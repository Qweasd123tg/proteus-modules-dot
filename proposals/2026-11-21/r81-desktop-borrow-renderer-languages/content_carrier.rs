// GPUI entity and process sender seams. Real set_source and populate_context are extracted.
use crate::declarative::protocol::{Outgoing, SurfaceKind};
pub(in crate::ui) struct WillResize;
pub(in crate::ui) struct ContentView {
    pub content: Arc<Content>,
    pub host: Host,
    layout_ready: LayoutReady,
    rendered: Entity<View>,
}
struct LayoutReady;
impl LayoutReady {
    fn set_ready(&self, ready:bool) { assert!(!ready); }
}
struct View { id:String }
fn emitted(id:&str, content:&Content)->String {
    serde_json::to_string(&Outgoing::Render {
        context:"fixture".to_owned(),view:id.to_owned(),surface:SurfaceKind::Content,
        content:Some(content.clone()),argument:Some("fixture-row".into()),session_dir:None,
    }).unwrap()
}
impl View {
    fn set_content(&mut self, content:Arc<Content>, _: &mut Window, cx:&mut Context<Self>) {
        let mut events=cx.events.borrow_mut();
        events.set_content += 1;
        events.wire.push(emitted(&self.id, &content));
    }
}
impl ContentView {
    pub(in crate::ui) fn body(host:Host, id:String,mut content:Content,_:&mut Window,cx:&mut Context<Self>)->Self {
        populate_context(&mut content.context, cx);
        let content=Arc::new(content);
        {
            let mut events=cx.events.borrow_mut();
            events.created+=1;
            events.wire.push(emitted(&id,&content));
        }
        let rendered=cx.new(|_|View{id});
        Self { content,host,layout_ready:LayoutReady,rendered }
    }
}
