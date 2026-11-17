fn ordered<'a>(saved: &[String], known: &[&'a str]) -> Vec<&'a str> {
    let mut ordered: Vec<&'a str> = saved
        .iter()
        .filter_map(|id| known.iter().find(|known| *known == id).copied())
        .collect();
    for id in known {
        if !ordered.contains(id) {
            ordered.push(id);
        }
    }
    ordered
}

fn move_before(saved: &mut Vec<String>, known: &[&str], id: &str, before: Option<&str>) {
    if before == Some(id) {
        return;
    }
    let mut items = ordered(saved, known);
    let Some(from) = items.iter().position(|item| *item == id) else {
        return;
    };
    let item = items.remove(from);
    let to = before
        .and_then(|before| items.iter().position(|item| *item == before))
        .unwrap_or(items.len());
    items.insert(to, item);
    *saved = items.into_iter().map(str::to_string).collect();
}
