use std::time::Duration;
thread_local!{ static CLOCK:std::cell::Cell<Duration>=const{std::cell::Cell::new(Duration::ZERO)}; }
struct Instant;
impl Instant {
    fn now()->Self{Self}
    fn elapsed(&self)->Duration{ CLOCK.with(std::cell::Cell::get) }
}
mod ui {
    mod ticker {
        use crate::Instant;
        use std::{time::Duration,sync::OnceLock};
        /*TICKER*/
    }
    pub(crate) fn at(t:std::time::Duration,p:std::time::Duration)->f32{
        crate::CLOCK.with(|c|c.set(t));ticker::phase(p)
    }
}
#[test]
fn one_turn_at_real_active_cadence() {
    let p=Duration::from_millis(1200);
    let mut summary=Vec::new();
    for days in [0,1,7,30,120] {
        let mut distinct=std::collections::BTreeSet::new();
        let mut err=0.0f64;
        for i in 0..36 {
            let t=Duration::from_secs(days*86_400)+Duration::from_nanos(i*1_200_000_000/36);
            let actual=ui::at(t,p);
            let expected=(t.as_nanos()%p.as_nanos()) as f64 / p.as_nanos() as f64;
            let distance=(actual as f64-expected).abs();
            err=err.max(distance.min(1.0-distance));
            distinct.insert(actual.to_bits());
        }
        println!("{days} days: {} distinct positions, max circular error {err:.9}",distinct.len());
        summary.push((distinct.len(),err));
    }
    assert!(summary.iter().all(|&(count,err)|count==36 && err<1e-6),"{summary:?}");
}
#[test]
fn just_before_wrap_stays_in_the_half_open_range() {
    for ms in [250,1200,1800] {
        let p=Duration::from_millis(ms);
        for t in [p-Duration::from_nanos(1),p,p+Duration::from_nanos(1)] {
            let a=ui::at(t,p);
            assert!((0.0..1.0).contains(&a));
        }
    }
}
