# ADR-0031. RC-1: відповідальність, цілі SLO/RPO/RTO і правило допуску

**Статус:** прийнято 2026-10-15. Рішення прийняв агент за прямим делегуванням власника
(«рішення можна приймати максимально автономно; відповідальність — на мені»). Моделі
переглядають цей ADR на кожному RC і з кожним новим виміром.
**Доповнює:** ADR-0020 (FlowSpec), ADR-0029 (пороги replay), SUPPORT, RUNBOOK, INDUSTRIAL.

## Відповідальність

- **Власник release, ризику й інцидентів — `s0fractal`.** Юридична відповідальність лежить
  на людині: моделі зараз не можуть її нести. Канал повідомлень — `SECURITY.md`.
- **Моделі** вирішують технічні питання самостійно в межах цього ADR: пропонують і
  змінюють цілі за вимірами, готують кандидатів, перевіряють правило допуску. Підпис
  власника (ADR-0023/0030) лишається єдиним, що відрізняє «агент заявив» від «прийнято».

## Як виведено цілі

Ціль = гірше виміряне значення в підтримуваному профілі (SUPPORT §1: Ubuntu 24.04,
XDP generic або native на veth, VM, до 30 вузлів) із запасом, що покриває інше залізо й
навантаження. Число без виміру позначене **ЦІЛЬ БЕЗ ВИМІРУ**: його перевірить пілот.
Жодна ціль не стосується native NIC чи upstream-маршрутизатора: ті лишаються
NOT_QUALIFIED, доки немає заліза.

## SLO

| # | Що | Виміряно (гірше) | Ціль | Джерело |
|---|---|---|---|---|
| S1 | Сигнал детектора → вузол перестає пропускати | 12 мс; 65 мс з netem 50 мс | ≤ 500 мс | reaction 2026-09-29, R1 |
| S2 | → кожен пір мешу перестає пропускати | 125 мс з netem 50 мс | ≤ 3 с | reaction, R2 |
| S3 | Зняття (RETRACT/UNBAN/FLUSH) → вузол знову пропускає | 13 мс; пір 12 мс | ≤ 1 с; пір ≤ 3 с | unblock 2026-10-15 |
| S4 | Кінець lease → XDP і піри | запис ≤ 966 мс після кінця + 12 мс; піри ≤ 59 мс | ≤ 2 с після підписаного кінця | unblock |
| S5 | Кінець блоку → правило FlowSpec зникає з RIB вузла | 2,03 с | ≤ 5 с для ≤ 64 змін; далі ⌈n/64⌉ раундів | unblock; ADR-0008 |
| S6 | Втрати легітимного трафіку під час блоків | 0,024 % (19 з 77 860) | ≤ 0,5 % | reaction, R4 |
| S7 | Керуючий сокет під флудом; тік; ремонт мешу після флуду | ≤ 1 с; тік ≤ 36 мс (soak 5 год) | ≤ 1 с; ≤ 500 мс; ≤ 120 с | recover L1–L3 2026-09-28 |
| S8 | Свіжість спостережень; незбережена зміна стану | алерти | знімок ≤ 5 с; ≤ 5 с | `InterdictSnapshotStale`, STALE_AFTER |
| S9 | Доступність процесу застосування (місяць) | — | 99,9 % (≤ 43 хв/міс) — **ЦІЛЬ БЕЗ ВИМІРУ** | `up`, `interdict_worker_state` |

Upstream FlowSpec (S5 за межами RIB вузла) не має цілі: RFC 8955 §6 і ADR-0020.

## RPO — що може бути втрачено при краху

| Дані | RPO | Чому |
|---|---|---|
| Рішення оператора й відкликання детектора, на які відповіли `OK` | 0 | на диску до відповіді (R26-04); інакше відповідь несе WARNING (DURABLE_WAIT 2 с) |
| Власні блоки детекторів | ≤ 5 с, поки стан здоровий | запис щотіку; довше — `interdict_state_pending_seconds`, DEGRADED |
| Заявки пірів | не зберігаються | повертаються з мешу за ≤ 2 періоди дайджесту (30 с) + знімок; межа — підписаний кінець |
| Журнал аудиту | ≤ 100 мс | fsync не пізніше SYNC_INTERVAL; втрати рахуються |
| Пороги replay мешу | до останнього запису стану | ADR-0029 |

## RTO — скільки до відновлення

| Подія | Виміряно | Ціль |
|---|---|---|
| Крах процесу (SIGKILL), блок на диску | сокет 115–163 мс, атакувальник проходить ≤ 80 мс, піри ≤ 1,12 с (3 і 10 вузлів, 20 раундів, без затримки systemd) | застосування ≤ 10 с з `RestartSec=2s`; меш ≤ 30 с; FlowSpec ≤ 10 с + ⌈n/64⌉ раундів |
| Пошкоджений файл стану | вузол DEGRADED до `ACCEPT_STATE_LOSS` | рішення оператора ≤ 15 хв — **ЦІЛЬ БЕЗ ВИМІРУ** |
| Втрата хоста | — | перевстановлення з архіву кандидата ≤ 1 год — **ЦІЛЬ БЕЗ ВИМІРУ** |

Крах: `docs/measurements/2026-10-15-restart` (`bench/mesh.sh restart`; контроль, що не
відновлює блок, падає на X2).

## Шкода хибного блоку

- Перший динамічний блок живе 900 с, повтори за 24 год подвоюють до 24 год
  (`--block-ttl`, `--block-ttl-max`); оператор знімає його за S3.
- Пілот починає в режимі спостереження (RUNBOOK §9, фаза 0). Перемикання на DROP — коли
  за щонайменше 7 днів тіні оператор визнав хибними ≤ 1 % рішень детекторів.
  **ЦІЛЬ БЕЗ ВИМІРУ**.

## Правило допуску RC

Кандидат — точний digest архіву (`scripts/candidate.py`), не гілка. RC-N допущено, коли
на цьому digest:

1. main зелений з усіма обов'язковими перевірками, gate `--every-pin`;
2. архів зібрано з inventory, атестація походження перевіряється
   (`gh attestation verify`);
3. репетиція RUNBOOK пройдена з пакета;
4. бенчі S1–S7 і `restart` перепрогнані на кандидаті й лежать у цілях;
5. кампанія на VM `scripts/campaign.py --profile rc1` — LIMITED_PASS: фаза хаосу (60 хв, рестарт
   вузла щохвилини, розріз кожні 90 с, TTL 180 с) і фаза плато (120 хв без рестартів,
   `SOAK_PLATEAU=1`: RSS і fds кожного вузла рівні, жоден блок не лишився pending; since
   2026-10-29 with the event memory saturated first and RSS and the state file judged against
   ceilings derived from the bounds, see the amendment of that date). Для RC-2 —
   ще й `--profile long` (24 год і 72 год);
6. немає відкритого P1; межі названі (native NIC, upstream FlowSpec — NOT_QUALIFIED; S7 at the
   bounds of the block table, amendment 2026-10-29). RC-2 also needs the state write at the
   bounds within S7 (same amendment).

Підтримка: RC-N підтримується до RC-N+1 або 90 днів, що раніше. Виправлення безпеки — лише
на останньому RC. Відповідь на повідомлення про вразливість — власник, ціль ≤ 7 днів
(**ЦІЛЬ БЕЗ ВИМІРУ**).

## Коли переглянути

Новий вимір, що виходить за ціль; пілот на справжньому залізі; новий RC. Ціль рухається
лише разом із виміром, що її обґрунтовує.

## Поправка 2026-10-28: правило 5 без добового очікування для RC-1

Чотири запуски 24 год (2026-10-15…21) зупинило середовище VM, а не вузол. Останній, на
кандидаті `776861e`, обірвав на 6,47 год `apt-daily-upgrade.timer` → `needrestart`.
Добовий прогін для RC-1 замінено двома стиснутими фазами (правило 5). `campaign.py` тепер
спершу зупиняє й маскує обслуговування VM (`apt-daily.timer`, `apt-daily-upgrade.timer`,
`unattended-upgrades.service`) і записує їхній стан у `report.json` (`quieted`).

Що з цим втрачено, і це межа RC-1: ефекти з періодом, довшим за три години кампанії
(повільний витік нижче 10 % за дві години, ротація журналів за розміром на добовому
обсязі, добові таймери хоста), RC-1 не бачить. Їх бачитиме RC-2 (`--profile long`).
Доведення Kani (`docs/VERIFICATION.md`) покривають арифметику часу в `common` для будь-якого
`u64`, але не ресурси процесу; вони не заміняють жодну з фаз.

TTL обох фаз — 180 с: пробний прогін 2026-10-28 на `4c5cf66` з TTL 30 с закінчився згодою вузлів
на порожній таблиці (усі блоки спливли за 90 с осідання), а така згода нічого не доводить. Тепер
`bench/mesh.sh` відмовляє в ній.

Фаза плато судить лише процес без рестартів: у фазі хаосу кожен вузол живе кілька хвилин,
і витік за одне життя процесу не встигає вирости. Тому фаз дві.


## Amendment 2026-10-29: the plateau is judged at the bounds

The plateau of rule 5 (amendment 2026-10-28) could not be decided within the campaign. Each table
a detector event fills keeps its entries up to 24 h: event ids and strikes for 24 h, claims and
their records up to `--block-ttl-max` (24 h) past their start. At the soak's 5 signals/s a node
needs about 11 h to fill its event memory alone, so during a 120 min phase these tables grow by
design, and "level within 10 %" measured how far they had filled, not whether anything leaked.
Rehearsals on 4c5cf66 (3 nodes, no restarts): ever-new addresses 120 min, 28 → 32 MB; 4 096
cycled addresses 60 min, 29 → 33 MB; 256 cycled addresses 45 min, 29.3 → 37.3 MB with a state
file of about 940 KB, failed on 2 of 3 nodes. The last one was not only filling: superseded
claims were held to their ends, fixed in ADR-0025's amendment of 2026-10-29.

**Rule 5's plateau phase now** (`scripts/campaign.py`, `bench/mesh.sh soak`):

1. **Saturate.** Before the load each node gets `MAX_EVENTS` + 4 096 signals with new event ids
   on the 256 cycled addresses, at the IPC's pace (about 70 s). Every node must then report
   evicted event ids (`interdict_event_ids_evicted_total` > 0): its event memory is full and
   stays full. The signals merge into the running claims, escalate them to `TTL_MAX` and fill
   each address's 8 reasons.
2. **Short lives.** TTL 180 s and `--block-ttl-max` 720 s: a claim lives at most 720 s, its
   retraction and lease records `FORGET_GRACE` (600 s) longer. From t = 1 320 s every table that
   follows claims is at its steady state for this load.
3. **Judge from t = 1 320 s** (98 one-minute samples per node): the last third's RSS and
   state-file peaks within 10 % of the first third's, fds not above the first third's peak;
   every sample's RSS within the node's own pre-load RSS + the derived bound, and the state
   file within the derived ceiling. A judged RSS, fd count or state size the sampler could not
   read, left empty or zero, fails the plateau: it is no level (`scripts/test_mesh_plateau.py`,
   Codex finding d398137c on #76). The bound and the ceiling are computed by `campaign.py` from
   the bounds in the code and the measured per-entry costs
   (`docs/measurements/2026-10-29-memory-at-bounds/bounds.json`; `scripts/test_campaign.py`
   refuses it when a bound changed): 518 MiB for every table at its bound + 2.8 MB of replay
   memory per peer (ADR-0013), and 228 MiB + the mesh floors. Planning numbers: RUNBOOK §4.

**Not driven, and why.** The strike memory's bound (65 536 addresses): filling it takes 65 536
new addresses, a claim on each on every node. A trial on 2026-10-29 did so; once those claims
were gone (256 blocks left) each node stayed at 313–362 MB RSS, because the allocator keeps the
freed heap resident, and step 3 could not see later growth under it. The strike bound is held by
`strike_memory_is_bounded_by_count`, and its cost (7.5 MB) is inside the derived bound. The
claim bound (`MAX_KNOWN_CLAIMS`) is likewise covered by its capacity tests and by
`measure_memory_at_all_bounds`, not by the campaign.

**What RC-1 still cannot see:** growth tied to claim lifetimes longer than 720 s, and anything
slower than 10 % in 98 min. RC-2's `--profile long` runs with the default `--block-ttl-max`.
On the lab VM (`docs/measurements/2026-10-29-memory-at-bounds/README.md` §4) the plateau passed
on this change's build, failed without the saturation (state file +32 % within the judged
window), and passed on the build before the ADR-0025 amendment of 2026-10-29 too: that
retention is tied to claim lifetimes, which 720 s bounds, so its tests are the evidence for it.

**Named RC-1 limit: S7 is not met with the block table at its bounds** (owner decision
2026-10-29). Derived ceilings with every table at its bound (RUNBOOK §4): RSS the node's own
idle RSS + 518 MiB + 2.8 MB per pinned peer, a state file of 228 MiB. Each tick in which the
table changed, `submit_state` copies its durable part (`take_persisted`) under the table lock
inside the maintenance tick: 0.12 s at 25 % of every bound, 0.25 s at 50 %, 0.38 s at 75 %,
0.57 s at 100 % (`measure_memory_at_all_bounds`, `MEASURE_SHARE`). Above about 85 % this step
alone keeps the tick past S7's 500 ms, and IPC answers and mesh adoption wait as long. Most of
it is the node's own claims and their records. To get there the node must hold close to
`MAX_KNOWN_CLAIMS` (262 144) claims at once: detectors reporting more than about 290 new
addresses per second for the first block's TTL (`--block-ttl`, 900 s), or the IPC's
2 000 lines/s of new addresses for about 2 min; with the RC-1 rehearsal's load (5 signals/s)
never. RC-1 ships with this limit named; `interdict_tick_seconds_max` shows an operator when a
node approaches it.

**RC-2 admission condition (added to rule 6):** with every table of the block table at its
bound, one state write keeps the maintenance tick within S7 (≤ 500 ms, measured by
`measure_memory_at_all_bounds` on the reference VM and by `interdict_tick_seconds_max` under
load). How is chosen by measurement: lower bounds, an incremental state file, or a copy taken
outside the table lock. ROADMAP item 0a.
