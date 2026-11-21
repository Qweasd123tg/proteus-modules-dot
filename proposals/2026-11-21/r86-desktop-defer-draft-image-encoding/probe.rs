#![allow(dead_code,unused_imports)]
mod image;
mod attachment_io;
mod attachments;
mod feedback;
mod carrier;
fn main() {
    let stamp=env!("R86_DRAFT_PROBE_ARM");
    eprintln!("ARM {stamp}");
    carrier::run(stamp.ends_with("/candidate"));
}
