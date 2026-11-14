#[path = "../../src/ui/chat/feedback/mod.rs"]
mod feedback;
use feedback::Feedback;
use proteus_contracts::domain::{ImageAttachment, ImageRef};
fn main() {
    let mut f = Feedback::default();
    let image_a = ImageAttachment { name:"clipboard.png".into(), mime_type:"image/png".into(), data:"a".into() };
    let image_b = ImageAttachment { name:"clipboard.png".into(), mime_type:"image/png".into(), data:"b".into() };
    f.begin("request-A".into(), "check this".into(), &[image_a], &[]);
    f.begin("request-B".into(), "check this".into(), &[image_b], &[]);
    // Independent HTTP background tasks can reach the server in reverse order.
    assert!(!f.complete("request-B", true, None));
    let echoed_b = ImageRef { id:"image-B".into(), name:"clipboard.png".into(), mime_type:"image/png".into(), path:"/synthetic/image-B.png".into() };
    f.submitted("check this", &[echoed_b]);
    let remaining: Vec<_> = f.visible_sends().map(|send| send.id.as_str()).collect();
    println!("B echoed, but pending receipt left = {remaining:?}");
    assert_eq!(remaining, vec!["request-B"]);
    // A fails before reaching Core. The UI must restore A, which has different image bytes.
    let restore_a = f.complete("request-A", false, None);
    println!("A failed; restore its draft = {restore_a}");
    assert!(!restore_a, "baseline changed: reverse-order send correlation is now protected");
    println!("REPRODUCED: B's echo suppresses A's failed-send recovery and notice");
}

#[cfg(test)]
mod audit_regressions {
    use super::*;
    #[test]
    fn rejected_send_must_be_recoverable_after_another_identical_send_echoes() {
        let mut f = Feedback::default();
        f.begin("A".into(), "repeat".into(), &[], &[]);
        f.begin("B".into(), "repeat".into(), &[], &[]);
        f.complete("B", true, None);
        f.submitted("repeat", &[]); // B arrives first; A never reached the server.
        assert!(f.complete("A", false, None), "A was not accepted and must be restored");
    }
}
