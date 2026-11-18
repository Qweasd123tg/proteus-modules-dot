mod panel;

use panel::Tally;
use proteus_extension::{Extension, Host, Result, Surface, Value, run};

impl Extension for Tally {
    fn render(&mut self, host: &mut Host, view: &str, surface: Surface, _: Option<&str>) -> Result {
        if surface == Surface::Panel {
            host.show(view, self.view());
        }
        Ok(())
    }

    fn action(&mut self, _: &mut Host, _: &str, action: &str, _: &Value) -> Result {
        self.act(action);
        Ok(())
    }
}

fn main() {
    run(Tally::default());
}
