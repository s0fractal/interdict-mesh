# ADR-0025. Частка пам'яті заявок на піра і резерв для власних рішень

**Статус:** реалізовано (варіант A, рішення власника 2026-10-10). **Дата:** 2026-10-10.

## Контекст

ADR-0007 обмежує, що пір може **застосувати** на цьому вузлі: `max_active` слотів, `max_ttl`,
найширший префікс, кворум. Але пам'ять знаних заявок одна на всіх: `MAX_KNOWN_CLAIMS`
(4 × ємність blocklist). Заявка, що чекає слота, тримається в цій пам'яті, і заявка без кінця
(`expires_ms: None`) не зникає ніколи.

Агентний пошук контрприкладів (раунд 3) показав: пір із конвертом в один слот надсилає 262 144
заявок без кінця (≈40 МБ, у межах транспортного бюджету). Конверт тримає: застосовано не більше
однієї. Проте через місяць власна детекція вузла і заявка третього вузла відхиляються з
`too many known claims`. Один скомпрометований вузол отримує необмежену владу над рештою, тобто
рівно те, від чого ADR-0007 мав захищати.

## Рішення

- **Частка на піра.** Нове поле конверту `max_known`: скільки заявок одного піра тримається тут
  водночас, застосованих чи ні. Типово `--peer-max-known` = 65 536 (одна ємність blocklist); у
  peers-файлі можна задати своє значення для окремого піра. Заявка понад частку відхиляється з
  `peer known-claims share full` і **не тримається**, тож пір може надіслати її знову, коли місце
  звільниться.
- **Резерв для власних рішень.** Заявки всіх пірів разом зупиняються на
  `MAX_KNOWN_CLAIMS − OWN_RESERVE`, де `OWN_RESERVE` = 65 536. Власні рішення вузла завжди мають
  щонайменше одну ємність blocklist місця, більше, ніж вузол може застосувати водночас.
- **Облік.** Кількість заявок на кожного видавця ведеться разом із `claims`: у єдиному місці
  вставки й у двох місцях видалення.

Зміна частки через `RELOAD_PEERS` відхиляється, якщо нова частка менша за кількість уже
збережених заявок піра. Відповідь — `ERR`; попередні конверти й trust store зберігаються.
Це не відкликає чужі рішення й не забуває строки їхніх оренд. Спершу потрібно дочекатися
звільнення місця або відкликання заявок, тоді повторити reload. Відкликання довіри до піра
не блокується: для його збережених записів лишається попередній конверт, але заявки відразу
перестають враховуватися при застосуванні блокувань. Довіра й нові конверти встановлюються
одним кроком під блокуванням таблиці.

## Відкинуті варіанти

- **Лише резерв (B).** Пір усе ще витісняє інших пірів.
- **Частка, пропорційна `max_active` (C).** Типово `max_active` = 16 384, а `Envelope::unlimited`
  нічого не обмежує. Пам'ять і повноваження — різні величини.

## Межі

- Понад три піри зі стелею за замовчуванням разом сягають спільної межі пірів. Тоді знову
  працює загальний ліміт, але власні рішення вузла лишаються вільними. Великому мешу варто
  зменшити `--peer-max-known`.
- Записи відкликань і далі мають одну спільну межу. Це свідоме обмеження з власними тестами;
  записи забуваються через `policy.max` + 600 с.
- Заявка без кінця від піра й далі тримається, доки її не відкличе видавець або оператор, але
  тепер лише в межах частки цього піра.

## Перевірка

- `a_one_slot_peer_cannot_deny_this_nodes_own_detections_by_volume`: повінь у 262 144 заявки
  зупиняється на частці піра, а власна детекція і заявка третього вузла через місяць проходять.
- `a_peer_beyond_its_known_claims_share_is_refused_alone`: відмова за частку має власну причину,
  а заявка іншого піра проходить.
- `peers_together_leave_the_room_kept_for_this_nodes_own_decisions`: піри без стелі разом
  зупиняються на `MAX_KNOWN_CLAIMS − OWN_RESERVE`, а власні рішення проходять.

- `a_reload_below_held_known_claims_keeps_the_previous_envelopes`: зменшення частки нижче
  збереженої кількості відхиляється для типової квоти й окремого піра.
- `a_reload_at_the_held_known_claims_bound_applies_and_ignores_own_claims`: рівність дозволена,
  власні заявки не підпадають під квоту піра, нульова частка відхиляє нові заявки.
- `a_refused_share_reload_answers_error_and_keeps_trust_then_can_be_retried`: справжній
  control-handler повертає `ERR`, зберігає довіру після відмови, дозволяє правильний повтор
  і не перешкоджає відкликанню довіри до піра з багатьма збереженими заявками.

Відновлення поведінки до виправлень провалює відповідні assertions (свідчення в PR).

## Amendment 2026-10-29: a claim its issuer took back is not held

**Found by measurement.** The RC-1 plateau rehearsal of 2026-10-28 (build 4c5cf66, 3 nodes,
signals cycling over 256 addresses, TTL 180 s) grew from 29.3 to 37.3 MB in 45 min with the
active blocks fixed at 256, wrote a state file of about 940 KB, and failed the plateau check on
2 of 3 nodes. A model of that run on three tables (`measure_memory_at_bounds`, 45 simulated
minutes) reproduced the state file (891 KB) and named the cause: 3 843 of node 1's 4 611 held
claims were claims their issuer had already superseded. A repeat that extends a block issues a
new claim and retracts the old one (R26-05); the old claim stayed held until its own end, up to
`--block-ttl-max` (24 h), on every node. Each cost 737 bytes of heap and its lease record 162
bytes next to the retraction record (218 bytes); on its issuer it was also saved in the state
file (119 bytes).

Memory was not the only cost. Such a claim counted against `MAX_KNOWN_CLAIMS` and against its
issuer's share here: a peer that escalates on 6 554 addresses ten times within a day fills its
65 536 share with claims that can never count again, and its new claims are refused with
`peer known-claims share full` until the old ones end.

**Decision.** When a retraction by a claim's own issuer is recorded (a live retraction, a
snapshot's retraction list, a superseding claim, an operator lift of this node's own claim),
the held claim is forgotten at once: it leaves `claims`, its target's index and its issuer's
count. Its retraction record stays, until `FORGET_GRACE` past the claim's end as
before (R26-03), and answers for every later copy: `adopt` answers `Held("retracted")` without
holding it, before any capacity or share check. A restore skips an own claim that a restored
record retracts (state files written before this change). A peer claim's lease record stays to
its own horizon (ADR-0003, R26-07): a peer's retraction is not saved here, so after a restart
that record is what still keeps a resent copy from a second lease (Codex finding 86291d96 on
#76, against a first form of this change that dropped it). Own claims have no lease record.
A peer's claim lifted only by this node's operator stays held: its issuer still asserts it, and
dropping it would make the digests differ and the snapshots repeat.

ADR-0001 (only the issuer retracts mesh-wide), ADR-0014 (an outcome names the earliest claim in
force, which a retracted claim never is) and ADR-0019 (a shortened block is reissued before the
old claims are retracted) are unchanged. Accounting: a held claim leaves `claims` in one
function, `forget_held` (its end, an operator claim lifted, a retraction by its issuer).

**Effect** (the same model, node 1 at 45 min): claims 4 611 → 768, heap 4.58 → 2.83 MB, state
file 891 → 740 KB.

**Checked by:** `a_claim_its_issuer_took_back_holds_no_share_here`,
`a_superseded_or_lifted_own_claim_leaves_the_table_and_the_state_file`,
`a_retracted_own_claim_in_an_older_state_file_is_not_held_again`; each failed on its
assertion before the change. `a_peer_claim_its_issuer_took_back_gets_no_second_lease_after_a_restart`
(LEASE-C1) failed on its assertion against the first form. `a_plain_lift_needs_no_free_claim_slot` (NODE-R2) now asserts the
slot the lifted claim frees.
