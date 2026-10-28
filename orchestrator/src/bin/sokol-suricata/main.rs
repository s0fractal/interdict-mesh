//! Transition alias for one merge (ADR-0034): the base gate runs the pinned Python witnesses with
//! the argument vectors of main's ci.yml, which still name `target/release/sokol-suricata` until this
//! rename is on main. It replaces itself with `interdict-suricata` from the same directory, so the
//! witnesses test the renamed adapter. Delete it in the first pull request after the merge.
use std::os::unix::process::CommandExt;

fn main() {
    let adapter = std::env::current_exe().map(|exe| exe.with_file_name("interdict-suricata"));
    let error = match adapter {
        Ok(path) => std::process::Command::new(path)
            .args(std::env::args_os().skip(1))
            .exec(),
        Err(error) => error,
    };
    eprintln!("sokol-suricata: cannot run interdict-suricata: {error}");
    std::process::exit(127);
}
