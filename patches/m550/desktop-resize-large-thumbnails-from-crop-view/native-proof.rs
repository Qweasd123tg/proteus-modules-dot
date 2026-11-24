extern crate self as gpui_kit;
use image::Frame;

/// Minimal GPUI upload boundary. The real pinned image Frame objects, BGRA
/// buffer and delays pass through unchanged. No atlas/display is simulated.
pub struct RenderImage(Vec<Frame>);
#[derive(Debug, PartialEq, Eq)]
pub struct Dimensions {
    pub width: Units,
    pub height: Units,
}
#[derive(Debug, PartialEq, Eq)]
pub struct Units(pub u32);
impl RenderImage {
    pub fn new(frames: Vec<Frame>) -> Self { Self(frames) }
    pub fn size(&self, n: usize) -> Dimensions {
        Dimensions { width: Units(self.0[n].buffer().width()), height: Units(self.0[n].buffer().height()) }
    }
    pub fn delay(&self, n: usize) -> image::Delay { self.0[n].delay() }
    pub fn as_bytes(&self, n: usize) -> Option<&[u8]> { self.0.get(n).map(|f| f.buffer().as_raw().as_slice()) }
    pub fn frame_count(&self) -> usize { self.0.len() }
}

mod stock;
mod candidate;

#[cfg(test)]
mod differential {
    use super::*;
    use image::{DynamicImage, ImageFormat, Rgb, RgbImage, Rgba, RgbaImage};
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::cell::Cell;
    use std::hint::black_box;
    use std::io::Cursor;
    use std::time::Instant;

    #[derive(Copy, Clone, Debug, Default)]
    struct Counts { net: isize, peak: isize, gross: usize, calls: usize }
    thread_local! { static METER: Cell<Option<Counts>> = const { Cell::new(None) }; }
    struct Meter;
    fn update(incoming: usize, outgoing: usize) {
        let _ = METER.try_with(|meter| {
            if let Some(mut c) = meter.get() {
                c.net += incoming as isize - outgoing as isize;
                c.peak = c.peak.max(c.net);
                c.gross += incoming;
                c.calls += usize::from(incoming > 0);
                meter.set(Some(c));
            }
        });
    }
    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let ptr = unsafe { System.alloc(layout) };
            if !ptr.is_null() { update(layout.size(), 0); }
            ptr
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            let ptr = unsafe { System.alloc_zeroed(layout) };
            if !ptr.is_null() { update(layout.size(), 0); }
            ptr
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            let ptr = unsafe { System.realloc(ptr, layout, new) };
            if !ptr.is_null() { update(new, layout.size()); }
            ptr
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            unsafe { System.dealloc(ptr, layout) };
            update(0, layout.size());
        }
    }
    #[global_allocator]
    static GLOBAL: Meter = Meter;

    fn scoped<T>(call: impl FnOnce() -> T) -> (T, Counts) {
        METER.with(|meter| assert!(meter.replace(Some(Counts::default())).is_none()));
        let out = call();
        let counts = METER.with(|meter| meter.replace(None).unwrap());
        (out, counts)
    }
    fn rgb(w: u32, h: u32) -> DynamicImage {
        RgbImage::from_fn(w,h, |x,y| Rgb([((x*73+y*19) as u8), ((x*11+y*53) as u8),
                                          ((x*y+11) as u8)])).into()
    }
    fn rgba(w: u32, h: u32) -> DynamicImage {
        RgbaImage::from_fn(w,h, |x,y| Rgba([((x*73+y*19) as u8), ((x*11+y*53) as u8),
                                           ((x*y+11) as u8),((x*23+y*31) as u8)])).into()
    }
    fn check_thumb(a: DynamicImage, edge: u32) {
        let x = stock::thumbnail_probe(a.clone(), edge);
        let y = candidate::thumbnail_probe(a, edge);
        assert_eq!(x.as_raw(), y.as_raw());
        assert_eq!(x.dimensions(), y.dimensions());
        assert_eq!(x.color_space(), y.color_space());
    }
    fn preview_pair(bytes: &[u8], edge: u32) {
        match (stock::prepare(bytes.to_vec(), edge), candidate::prepare(bytes.to_vec(), edge)) {
            (Ok(x), Ok(y)) => {
                assert_eq!(x.pixels, y.pixels);
                assert_eq!(x.image.frame_count(), y.image.frame_count());
                for (a,b) in x.image.0.iter().zip(&y.image.0) {
                    assert_eq!(a.delay(),b.delay());
                    assert_eq!(a.left(),b.left()); assert_eq!(a.top(),b.top());
                    assert_eq!(a.buffer().dimensions(),b.buffer().dimensions());
                    assert_eq!(a.buffer().as_raw(),b.buffer().as_raw());
                    assert_eq!(a.buffer().color_space(),b.buffer().color_space());
                }
            }
            (Err(x), Err(y)) => assert_eq!(x.to_string(),y.to_string()),
            _ => panic!("preview outcomes differ")
        }
    }
    fn encode(a: &DynamicImage, format: ImageFormat) -> Vec<u8> {
        let mut b=Cursor::new(vec![]);
        a.write_to(&mut b,format).unwrap();
        b.into_inner()
    }
    fn jpeg_exif_rot90(mut b: Vec<u8>) -> Vec<u8> {
        let exif = b"Exif\0\0II*\0\x08\0\0\0\x01\0\x12\x01\x03\0\x01\0\0\0\x06\0\0\0\0\0\0\0";
        let mut out=b[..2].to_vec();
        out.extend_from_slice(&[0xff,0xe1]);
        out.extend_from_slice(&((exif.len()+2) as u16).to_be_bytes());
        out.extend_from_slice(exif);
        out.extend(b.drain(2..));
        out
    }

    #[test]
    fn pixel_pattern_strides_thresholds_color_and_fallbacks() {
        for (w,h,e) in [(39,31,4),(39,32,4),(31,39,4),(32,39,4),(39,33,4),
                        (64,64,8),(3,7,7),(32768,1,384),(1,32768,384),(801,1200,96),
                        (1200,801,96),(20,16,2),(20,17,1),(20,15,1)] {
            check_thumb(rgb(w,h),e);
            check_thumb(rgba(w,h),e);
        }
        let mut img=rgba(2048,1025);
        img.set_color_space(image::metadata::Cicp::DISPLAY_P3).unwrap();
        check_thumb(img,128);
        let mut img=rgb(1025,2048);
        img.set_color_space(image::metadata::Cicp::DISPLAY_P3).unwrap();
        check_thumb(img,128);
        let hicolor=image::ImageBuffer::<image::Rgba<u16>,Vec<u16>>::from_fn(257,129,|x,y|
                                     image::Rgba([x as u16*250, y as u16*500,(x+y) as u16*170,60000]));
        check_thumb(DynamicImage::ImageRgba16(hicolor),16);
    }

    #[test]
    fn wire_png_jpeg_rotated_animated_and_failures() {
        let color=rgba(1591,785);
        preview_pair(&encode(&color,ImageFormat::Png),96);
        let color=rgb(1577,781);
        preview_pair(&encode(&color,ImageFormat::Jpeg),96);
        preview_pair(&jpeg_exif_rot90(encode(&color,ImageFormat::Jpeg)),96);
        let mut gif=vec![];
        {
          let mut enc=image::codecs::gif::GifEncoder::new(&mut gif);
          enc.encode_frames((0usize..5).map(|n| {
              let frame=RgbaImage::from_fn(137,129,|x,y| {
                  let i=(x as usize*23+y as usize*75+n*37)%4;
                  Rgba([[10,100,200,255],[20,50,230,255],[39,224,78,0],[90,40,212,255]][i])
              });
              Frame::from_parts(frame,0,0,image::Delay::from_numer_denom_ms((1+n as u32)*10,1))
          })).unwrap();
        }
        preview_pair(&gif,16);
        preview_pair(include_bytes!("stock/testdata/animated-40.webp"),384);
        preview_pair(include_bytes!("stock/testdata/overlong-257.webp"),96);
        preview_pair(b"broken image",96);
        preview_pair(&gif[..14],16);
        let mut oversized=gif;
        oversized[6..8].copy_from_slice(&32768u16.to_le_bytes());
        oversized[8..10].copy_from_slice(&32768u16.to_le_bytes());
        preview_pair(&oversized,16);
    }

    fn meter_row(name: &str, src: DynamicImage, edge: u32, minimum_saved: isize) {
        let (a,x) = scoped(|| stock::thumbnail_probe(src.clone(),edge));
        let (b,y) = scoped(|| candidate::thumbnail_probe(src.clone(),edge));
        assert_eq!(a.as_raw(),b.as_raw());
        assert_eq!(x.net,y.net);
        if minimum_saved > 0 {
           assert!(x.peak-y.peak > minimum_saved,"{name}: {x:?} / {y:?}");
        } else {
           assert_eq!(x.peak,y.peak,"{name}: {x:?} / {y:?}");
        }
        println!("ALLOC {name} stock_peak={} candidate_peak={} stock_gross={} candidate_gross={} retained_equal={} calls_stock={} calls_new={}",x.peak,y.peak,x.gross,y.gross,y.net,x.calls,y.calls);
    }
    #[test]
    fn scoped_requested_allocation_peak() {
        meter_row("rgba-6144x4096-edge384",rgba(6144,4096),384,10_000_000);
        meter_row("rgb-6133x4151-edge384",rgb(6133,4151),384,10_000_000);
        meter_row("rgb-owner-2048x1024-edge96",rgb(2048,1024),96,1_000_000);
        meter_row("thin-32768x1-edge384",rgba(32768,1),384,0);
        meter_row("near-square-1024x1023-edge384",rgba(1024,1023),384,0);
        meter_row("rgba-16bit-1519x1304-edge96", DynamicImage::ImageRgba16(
            image::ImageBuffer::from_pixel(1519,1304,image::Rgba([10u16,20,30,40]))),96,0);
    }
    fn ms_ns(f: impl FnOnce()->RgbaImage) -> u128 {
        let t=Instant::now();
        let result=black_box(f());
        let nanos=t.elapsed().as_nanos();
        black_box(result);
        nanos
    }
    #[test]
    #[ignore = "run separately, pinned CPU with no competing jobs"]
    fn paired_resize_timing_unmetered() {
        for (name,source,edge) in [("rgba-big-edge384",rgba(6144,4096),384),
            ("rgb-big-edge384",rgb(6133,4151),384),
            ("rgba-owner-shaped-edge96",rgba(2048,1024),96),
            ("rgba-shaped-edge192-fallback",rgba(2048,1024),192)] {
           let mut rows=vec![];
           for n in 0..9 {
                let a=source.clone();
                let b=source.clone();
                let (x,y)=if n%2==0 {
                    let x=ms_ns(||stock::thumbnail_probe(a,edge));
                    let y=ms_ns(||candidate::thumbnail_probe(b,edge));(x,y)
                } else {
                    let y=ms_ns(||candidate::thumbnail_probe(b,edge));
                    let x=ms_ns(||stock::thumbnail_probe(a,edge));(x,y)
                };
                rows.push((x,y));
            }
            println!("TIMING {name} pairs_ns={rows:?}");
        }
    }
}
