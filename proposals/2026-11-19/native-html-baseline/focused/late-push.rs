    fn opted_late_push_keeps_fragment_semantics(cx: &mut TestAppContext) {
        cx.update(crate::init);
        let prefix = "<p><b>old";
        let suffix = "new</b></p>";
        let eager = cx.update(|cx| cx.new(|cx| TextViewState::html(prefix, cx)));
        let opted = cx.update(|cx| cx.new(|cx| TextViewState::html_for_replacements(prefix, cx)));
        cx.run_until_parked();

        eager.read_with(cx, |s,_| assert!(!s.defer_html_baseline));
        opted.read_with(cx, |s,_| assert!(s.defer_html_baseline && s.is_ready()));
        for view in [&eager, &opted] {
            view.update(cx, |s,cx| s.push_str(suffix, cx));
        }
        cx.run_until_parked();
        let state = |s: &TextViewState| (s.parsed_content.document.clone(),
            s.rendered_text().as_str().to_string(), s.revision, s.committed_revision, s.selection_revision);
        let expected = eager.read_with(cx, |s,_| state(s));
        let actual = opted.read_with(cx, |s,_| state(s));
        assert_eq!(expected, actual);
        let whole = cx.update(|cx| cx.new(|cx| TextViewState::html(&format!("{prefix}{suffix}"), cx)));
        cx.run_until_parked();
        let full = whole.read_with(cx, |s,_| state(s));
        assert_ne!(actual.0.blocks, full.0.blocks);
    }
