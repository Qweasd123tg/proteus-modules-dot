#![allow(dead_code, unused_imports)]
extern crate self as gpui_kit;
extern crate self as proteus_contracts;

use std::cell::Cell;
use std::sync::Arc;

#[cfg(test)]
mod counter;
use proteus_diff as diff;

pub mod app_protocol {
    pub mod settings;
}

pub mod assets {
    /// Only icon data is modeled, not the production Node/type checks.
    #[derive(Clone, Copy)]
    pub struct IconName(&'static str);
    impl IconName {
        pub const ALL: &'static [Self] = &[
            Self("icons/git-branch.svg"),
            Self("icons/file-code.svg"),
            Self("icons/refresh-cw.svg"),
            Self("icons/arrow-up.svg"),
            Self("icons/copy.svg"),
        ];
        pub fn path(self) -> &'static str {
            self.0
        }
    }
}

mod declarative {
    pub mod control;
    pub mod graph;
    pub mod icons;
    pub mod lanes;
    pub mod list;
    pub mod presentation;
    pub mod protocol;
    pub mod svg;
    pub mod tree;
    pub mod widget;
}

pub struct App;

impl App {
    pub fn svg_renderer(&self) -> SvgRenderer {
        SvgRenderer::default()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DevicePixels(pub i32);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Size<P> {
    pub width: P,
    pub height: P,
}

pub fn size<P>(width: P, height: P) -> Size<P> {
    Size { width, height }
}

pub enum SvgSize {
    ExactSize(Size<DevicePixels>),
}

pub struct RenderImage(pub Size<DevicePixels>, pub u64);

pub struct ParsedSvg(u64);

#[derive(Default)]
pub struct SvgRenderer {
    pub parsed: Cell<usize>,
    pub painted: Cell<usize>,
}
impl SvgRenderer {
    /// An inert native effect: receives and fingerprints exact validated
    /// bytes, never parses or draws SVG. Any rejection is the test marker.
    pub fn parse_svg(&self, bytes: &[u8]) -> Result<ParsedSvg, &'static str> {
        self.parsed.set(self.parsed.get() + 1);
        let source = std::str::from_utf8(bytes).unwrap();
        assert!(source.starts_with("<svg"));
        if source.contains("fixture-refuse-parse") {
            return Err("inert parse refusal");
        }
        Ok(ParsedSvg(fingerprint(bytes)))
    }

    pub fn render_parsed(
        &self,
        svg: &ParsedSvg,
        size: SvgSize,
    ) -> Result<Arc<RenderImage>, &'static str> {
        self.painted.set(self.painted.get() + 1);
        let SvgSize::ExactSize(size) = size;
        if size.width.0 == 7 {
            return Err("inert raster refusal");
        }
        Ok(Arc::new(RenderImage(size, svg.0)))
    }
}

fn fingerprint(bytes: &[u8]) -> u64 {
    bytes.iter().fold(14695981039346656037, |h, b| {
        (h ^ u64::from(*b)).wrapping_mul(1099511628211)
    })
}

mod ui {
    pub mod render_image {
        use crate::{App, RenderImage};
        use std::sync::Arc;

        pub struct Bitmap(pub Arc<RenderImage>);
        impl Bitmap {
            pub fn new(image: Arc<RenderImage>, _: Option<&App>) -> Arc<Self> {
                Arc::new(Self(image))
            }
        }
    }
}

mod images;
