// Diagnostic only; append to vendor/gpui-base/src/text/state.rs.
impl TextViewState {
    pub fn r5_check_selection_alias() {
        let parse = || format::markdown::parse("two words", &mut NodeContext::default()).unwrap();
        let a = parse();
        let b = a.clone();
        let copied_blocks = Arc::new((*a.blocks).clone());
        let fresh = parse();
        let node::BlockNode::Paragraph(p) = &a.blocks[0] else { panic!("fixture must be a paragraph") };
        assert!(Arc::ptr_eq(&a.blocks, &b.blocks));
        assert!(!Arc::ptr_eq(&a.blocks, &copied_blocks));
        p.state.lock().unwrap().selection = Some((0..3).into());
        assert!(b.blocks[0].has_selection());
        assert!(copied_blocks[0].has_selection());
        assert!(!fresh.blocks[0].has_selection());
        copied_blocks[0].clear_selection();
        assert!(!a.blocks[0].has_selection());
        println!("R5 alias: parsed document clone AND deep-copied block vector share paragraph selection; independent parse does not; clearing the copy clears the original");
    }
}
