#![allow(dead_code)]
const APP_ID: &str = "dev.proteus.native";
mod meter;
mod ui {
    mod chat {
        mod scroller {
            mod scrollbar {
                const UNKNOWN_ROW_HEIGHT: f32 = 100.;
                mod height_cache;
                mod height_map;
                mod height_store;
            }
        }
    }
}
