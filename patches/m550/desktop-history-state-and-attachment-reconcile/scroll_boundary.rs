use crate::*;
use std::cell::{Cell,RefCell};
type Pixels = f32;
#[derive(Default,Debug,PartialEq)]
pub(crate) struct Geometry {
    pub(crate) represented: Option<HistoryRange>,
    pub(crate) released: usize,
    pub(crate) rebased: usize,
}
impl Geometry {
    fn rebase(&mut self, _:Option<usize>) {self.rebased += 1;self.represented=None;}
    fn release_pin(&mut self) {self.released+=1;}
    fn represents(&self,range:HistoryRange)->bool {self.represented==Some(range)}
}
#[derive(Default)]
pub(crate) struct NativeList(Cell<usize>);
impl NativeList { fn scrollbar_drag_ended(&self){self.0.set(self.0.get()+1);} }
#[derive(Default)]
pub(crate) struct Measurements { pub(crate) set: usize, pub(crate) range: Option<HistoryRange> }
impl Measurements {
    fn set_range(&mut self, range:Option<HistoryRange>) {self.set+=1;self.range=range;}
}
#[derive(Default)]
pub(crate) struct HistoryScrollbar {
    list: NativeList,
    state: Cell<State>,
    geometry: RefCell<Geometry>,
    measurements: RefCell<Measurements>,
    footer: Cell<Option<Pixels>>,
}
impl HistoryScrollbar {
    pub(crate) fn telemetry(&self) -> (usize,usize,usize,usize,bool,Option<usize>) {
        let geo=self.geometry.borrow(); let s=self.state.get();
        (self.measurements.borrow().set,geo.rebased,geo.released,self.list.0.get(),s.waiting,s.displayed.map(|(t,_)|t.row))
    }
    pub(crate) fn waiting(&self, row:usize, drag:bool) {
        let mut s=self.state.get();s.waiting=true;
        s.displayed=Some((crate::ScrollTarget{row,fraction:0.25},12.));
        s.seek_height=Some(100.); s.drag_height=drag.then_some(100.);
        self.state.set(s);self.geometry.borrow_mut().represented=s.range;
    }
    pub(crate) fn set_following_seed(&self, range:crate::HistoryRange) {
        let mut state=self.state.get();state.range=Some(range);self.state.set(state);
        self.geometry.borrow_mut().represented=Some(range);
    }
}
