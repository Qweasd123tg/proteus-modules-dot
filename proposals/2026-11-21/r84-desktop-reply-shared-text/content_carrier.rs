// Mount and GPUI entity seams; source update and runtime rendering are real.
use crate::declarative::protocol::SurfaceKind;
use super::runtime_probe::{Capture,Runtime};
pub(in crate::ui) struct WillResize;
pub(in crate::ui) struct ContentView {
    pub content: Arc<Content>,
    pub host: Host,
    layout_ready: LayoutReady,
    rendered: Entity<View>,
}
struct LayoutReady;
impl LayoutReady {fn set_ready(&self,ready:bool){assert!(!ready);}}
struct View {id:String, runtime:Runtime}
impl View {
    fn set_content(&mut self,content:Arc<Content>,_:&mut Window,cx:&mut Context<Self>){
        cx.events.borrow_mut().set_content+=1;
        self.runtime.set_content(&self.id,content,cx);
    }
}
impl ContentView {
    pub(in crate::ui) fn body(host:Host,id:String,mut content:Content,_:&mut Window,cx:&mut Context<Self>)->Self{
        populate_context(&mut content.context,cx);
        let content=Arc::new(content);
        cx.events.borrow_mut().created+=1;
        let mut runtime=Runtime::new(&id,SurfaceKind::Content,Some(content.clone()),!host.readonly);
        runtime.draw(&id,cx);
        let rendered=cx.new(|_| View{id,runtime});
        Self {content,host,layout_ready:LayoutReady,rendered}
    }
    pub fn capture(&self)->Rc<Capture>{self.rendered.0.borrow().runtime.capture.clone()}
    pub fn ack(&self,revision:Option<u64>,cx:&App){
        let view=&mut *self.rendered.0.borrow_mut();
        view.runtime.acknowledge(&view.id,revision,cx);
    }
    pub fn draw(&self,cx:&App){
        let view=&mut *self.rendered.0.borrow_mut();
        view.runtime.draw(&view.id,cx);
    }
    pub fn restart(&self,cx:&App){
        let view=&mut *self.rendered.0.borrow_mut();
        view.runtime.restart(&view.id,cx);
    }
    pub fn runtime_content(&self)->Arc<Content>{
        let view=self.rendered.0.borrow();
        view.runtime.content(&view.id).unwrap().clone()
    }
}
