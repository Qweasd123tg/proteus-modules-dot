
#[cfg(test)]
mod owned_widget_arrays {
    use super::*;

    #[test]
    fn tree_and_fill_move_rows_without_changing_wire_order() {
        let rows = vec![json!({"name":"Файл","items":["link",null,true]})];
        let row_ptr = rows.as_ptr();
        let string_ptr = rows[0]["name"].as_str().unwrap().as_ptr();
        let children = vec![tree("files", rows, "open")];
        let child_ptr = children.as_ptr();
        let node = fill(children);
        assert_eq!(node["children"].as_array().unwrap().as_ptr(), child_ptr);
        assert_eq!(node["children"][0]["rows"].as_array().unwrap().as_ptr(), row_ptr);
        assert_eq!(node["children"][0]["rows"][0]["name"].as_str().unwrap().as_ptr(), string_ptr);
        assert_eq!(node.to_string(), r#"{"type":"fill","children":[{"type":"tree","id":"files","rows":[{"name":"Файл","items":["link",null,true]}],"action":"open"}]}"#);
    }
}
