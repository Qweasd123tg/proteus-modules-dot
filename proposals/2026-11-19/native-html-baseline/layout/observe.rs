use gpui::{prelude::*, *};
use gpui_base::text::{TextView, TextViewState};
use serde_json::json;

struct Root(Entity<TextViewState>);
impl Render for Root {
    fn render(&mut self, _: &mut Window, _: &mut Context<Self>) -> impl IntoElement {
        div().id("fixture").flex().flex_col().w(px(320.)).child(
            TextView::new(&self.0).selectable(true)
        ).child(div().id("sentinel").debug_selector(|| "sentinel".into())
            .h(px(7.)).bg(rgb(0xcc4422)))
    }
}
fn measure(stage: &str, state: &Entity<TextViewState>, cx: &mut VisualTestContext) {
    let (q,u)=cx.update(|w,cx| {
        w.draw(cx).clear(cx);
        (w.painted_quads().len(), w.painted_underlines().len())
    });
    let sentinel = cx.debug_bounds("sentinel").expect("sentinel has layout");
    let record=state.read_with(cx,|s,_| {
        let bounds=s.bounds();
        json!({"stage":stage,"width":f32::from(bounds.size.width),"height":f32::from(bounds.size.height),
           "sentinel_y": f32::from(sentinel.origin.y),"sentinel_h": f32::from(sentinel.size.height),
           "ready":s.is_ready(),"rendered":s.rendered_text().as_str(),"selected":s.selected_text(),
           "scene_quads":q,"scene_underlines":u})
    });
    assert!(q>0 && sentinel.size.height==px(7.));
    println!("{record}");
}
fn main() {
    let mut app=TestAppContext::single();
    app.update(gpui_base::init);
    let (root,cx)=app.add_window_view(|_,cx| Root(cx.new(|cx| TextViewState::html("<p>Seed.</p>",cx).scrollable(false))));
    let state=root.read_with(cx,|r,_| r.0.clone());
    let rich="<h2>Geometry</h2><p>Sober <strong>bold</strong> and <a href=\"https://example.org\">link</a>.</p><p>Third paragraph.</p>";
    state.update(cx,|s,cx|s.set_text(rich,cx));
    measure("short-immediate",&state,cx);
    cx.run_until_parked();
    measure("short-idle",&state,cx);
    state.update(cx,|s,cx|s.select_all(cx));
    measure("selected",&state,cx);
    state.update(cx,|s,cx|s.set_text("<table><tr><th>key</th><th>value</th></tr><tr><td>A</td><td>B</td></tr></table>",cx));
    measure("table-immediate",&state,cx);
    cx.run_until_parked(); measure("table-idle",&state,cx);
    for html in ["<p>obsolete-one</p>", "<p>obsolete-two</p>", "<b>red"] {
       state.update(cx,|s,cx|s.set_text(html,cx));
    }
    measure("supersede-immediate",&state,cx);
    cx.run_until_parked(); measure("supersede-idle",&state,cx);
    state.update(cx,|s,cx|s.push_str("<p>new independent fragment</p>",cx));
    cx.run_until_parked(); measure("append-idle",&state,cx);
}
