#![allow(dead_code)]
use anyhow::Result;
use image::{imageops, ImageFormat, Rgb, RgbImage};
use std::io::Cursor;

pub const MAX_SIDE: u32 = 1568;

#[derive(Debug, Clone, Copy)]
pub struct View {
    pub left: i32,
    pub top: i32,
    pub scale: f64,
    pub width: u32,
    pub height: u32,
}

impl View {
    pub fn new(left: i32, top: i32, scale: f64, width: u32, height: u32) -> Self {
        Self {
            left,
            top,
            scale,
            width,
            height,
        }
    }

    pub fn to_screen(&self, x: f64, y: f64) -> Result<(i32, i32)> {
        if x < 0.0 || x >= self.width as f64 || y < 0.0 || y >= self.height as f64 {
            anyhow::bail!(
                "Point ({}, {}) is outside image bounds ({}x{})",
                x,
                y,
                self.width,
                self.height
            );
        }
        let sx = (self.left as f64 + x * self.scale).round() as i32;
        let sy = (self.top as f64 + y * self.scale).round() as i32;
        Ok((sx, sy))
    }

    pub fn rect_to_screen(&self, x: f64, y: f64, w: f64, h: f64) -> (i32, i32, i32, i32) {
        let (x0, y0) = self.to_screen(x.max(0.0), y.max(0.0)).unwrap_or((self.left, self.top));
        let x1 = (self.left as f64 + (x + w) * self.scale).round() as i32;
        let y1 = (self.top as f64 + (y + h) * self.scale).round() as i32;
        let max_w = (self.width as f64 * self.scale).round() as i32;
        let max_h = (self.height as f64 * self.scale).round() as i32;
        (
            x0,
            y0,
            (x1 - x0).clamp(1, max_w),
            (y1 - y0).clamp(1, max_h),
        )
    }
}

pub fn decode_rgb(bytes: &[u8]) -> Result<RgbImage> {
    let img = image::load_from_memory_with_format(bytes, ImageFormat::Jpeg)?;
    Ok(img.to_rgb8())
}

pub fn encode_jpeg(img: &RgbImage, quality: u8) -> Result<Vec<u8>> {
    let mut out = Cursor::new(Vec::with_capacity(img.width() as usize * img.height() as usize / 4));
    let mut encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, quality);
    encoder.encode_image(img)?;
    Ok(out.into_inner())
}

/// Computes the bounding box [x, y, w, h] of changed pixels between two JPEG images.
pub fn detect_change_bbox(
    before_bytes: &[u8],
    after_bytes: &[u8],
    threshold: u8,
    padding: u32,
) -> Result<Option<[u32; 4]>> {
    let img1 = decode_rgb(before_bytes)?;
    let img2 = decode_rgb(after_bytes)?;

    if img1.dimensions() != img2.dimensions() {
        return Ok(Some([0, 0, img2.width(), img2.height()]));
    }

    let (w, h) = img1.dimensions();
    let mut min_x = u32::MAX;
    let mut max_x = 0;
    let mut min_y = u32::MAX;
    let mut max_y = 0;

    let p1 = img1.as_raw();
    let p2 = img2.as_raw();

    for y in 0..h {
        let row_offset = (y * w * 3) as usize;
        for x in 0..w {
            let offset = row_offset + (x * 3) as usize;
            let dr = p1[offset].abs_diff(p2[offset]);
            let dg = p1[offset + 1].abs_diff(p2[offset + 1]);
            let db = p1[offset + 2].abs_diff(p2[offset + 2]);

            if dr > threshold || dg > threshold || db > threshold {
                min_x = min_x.min(x);
                max_x = max_x.max(x);
                min_y = min_y.min(y);
                max_y = max_y.max(y);
            }
        }
    }

    if min_x > max_x || min_y > max_y {
        return Ok(None);
    }

    let pad_x0 = min_x.saturating_sub(padding);
    let pad_y0 = min_y.saturating_sub(padding);
    let pad_x1 = (max_x + padding).min(w.saturating_sub(1));
    let pad_y1 = (max_y + padding).min(h.saturating_sub(1));

    Ok(Some([
        pad_x0,
        pad_y0,
        pad_x1.saturating_sub(pad_x0).max(1),
        pad_y1.saturating_sub(pad_y0).max(1),
    ]))
}

/// A rectangle in image pixels: [x, y, w, h].
pub type Roi = [u32; 4];

/// Default modal-detection region: the top resource bar of a 1568-wide frame.
pub const DEFAULT_MODAL_ROI: Roi = [0, 0, 500, 35];

/// Convert a normalized rectangle (fractions of width/height) to image pixels, clamped.
pub fn roi_from_norm(width: u32, height: u32, norm: [f64; 4]) -> Roi {
    let x = (norm[0].clamp(0.0, 1.0) * width as f64).round() as u32;
    let y = (norm[1].clamp(0.0, 1.0) * height as f64).round() as u32;
    let w = ((norm[2].max(0.0) * width as f64).round() as u32).max(1);
    let h = ((norm[3].max(0.0) * height as f64).round() as u32).max(1);
    clamp_roi([x, y, w, h], width, height)
}

pub fn clamp_roi(roi: Roi, width: u32, height: u32) -> Roi {
    let x = roi[0].min(width.saturating_sub(1));
    let y = roi[1].min(height.saturating_sub(1));
    [x, y, roi[2].min(width - x).max(1), roi[3].min(height - y).max(1)]
}

/// Mean ITU-R BT.601 luminance (0..255) over a region.
pub fn region_mean_luminance(img: &RgbImage, roi: Roi) -> f64 {
    let [x0, y0, w, h] = clamp_roi(roi, img.width(), img.height());
    let mut sum = 0.0;
    for y in y0..y0 + h {
        for x in x0..x0 + w {
            let p = img.get_pixel(x, y);
            sum += 0.299 * p[0] as f64 + 0.587 * p[1] as f64 + 0.114 * p[2] as f64;
        }
    }
    sum / (w * h) as f64
}

/// Mean absolute per-channel difference over a region, normalized to 0..1.
/// 0 = identical; small UI text changing in place scores well above 0.05.
pub fn region_diff(a: &RgbImage, b: &RgbImage, roi: Roi) -> f64 {
    let w = a.width().min(b.width());
    let h = a.height().min(b.height());
    let [x0, y0, rw, rh] = clamp_roi(roi, w, h);
    let mut sum: u64 = 0;
    for y in y0..y0 + rh {
        for x in x0..x0 + rw {
            let pa = a.get_pixel(x, y);
            let pb = b.get_pixel(x, y);
            for c in 0..3 {
                sum += (pa[c] as i32 - pb[c] as i32).unsigned_abs() as u64;
            }
        }
    }
    sum as f64 / (rw as f64 * rh as f64 * 3.0 * 255.0)
}

/// Largest mean luminance difference (0..1) over any `strip_w`-pixel-wide vertical strip of
/// `roi`. Sized to one glyph, so a single changed character in a text readout scores as high
/// as a whole-string change, while JPEG noise stays near 0.
///
/// Measured on real GC4 frames (date readout, 78x25 px): identical dates <= 0.003;
/// "Apr 2" -> "Aug 2" = 0.101 (the whole-box mean was only 0.028).
pub fn region_diff_max_strip(a: &RgbImage, b: &RgbImage, roi: Roi, strip_w: u32) -> f64 {
    let w = a.width().min(b.width());
    let h = a.height().min(b.height());
    let [x0, y0, rw, rh] = clamp_roi(roi, w, h);
    let lum = |p: &Rgb<u8>| 0.299 * p[0] as f64 + 0.587 * p[1] as f64 + 0.114 * p[2] as f64;
    // Per-column sums of |luminance difference|, then a sliding window over columns.
    let cols: Vec<f64> = (x0..x0 + rw)
        .map(|x| (y0..y0 + rh).map(|y| (lum(a.get_pixel(x, y)) - lum(b.get_pixel(x, y))).abs()).sum())
        .collect();
    let sw = strip_w.clamp(1, rw) as usize;
    let mut window: f64 = cols[..sw].iter().sum();
    let mut best = window;
    for i in sw..cols.len() {
        window += cols[i] - cols[i - sw];
        best = best.max(window);
    }
    best / (sw as f64 * rh as f64 * 255.0)
}

/// Fraction (0..1) of pixels in `roi` ([x, y, w, h], clamped to the frame) whose colour lies
/// within `range` ([min rgb, max rgb], inclusive).
pub fn color_fraction(frame: &RgbImage, roi: Roi, range: [[u8; 3]; 2]) -> f64 {
    let [x, y, w, h] = clamp_roi(roi, frame.width(), frame.height());
    if w == 0 || h == 0 {
        return 0.0;
    }
    let mut hits = 0u64;
    for py in y..y + h {
        for px in x..x + w {
            let p = frame.get_pixel(px, py);
            if (0..3).all(|c| p[c] >= range[0][c] && p[c] <= range[1][c]) {
                hits += 1;
            }
        }
    }
    hits as f64 / (w as f64 * h as f64)
}

#[cfg(test)]
mod color_tests {
    use super::*;
    #[test]
    fn color_fraction_counts_pixels_in_range() {
        let mut f = RgbImage::from_pixel(10, 10, image::Rgb([0, 0, 0]));
        for x in 0..5 {
            for y in 0..10 {
                f.put_pixel(x, y, image::Rgb([220, 200, 40]));
            }
        }
        let yellow = [[150, 120, 0], [255, 255, 110]];
        assert!((color_fraction(&f, [0, 0, 10, 10], yellow) - 0.5).abs() < 1e-9);
        assert_eq!(color_fraction(&f, [5, 0, 5, 10], yellow), 0.0);
        assert_eq!(color_fraction(&f, [20, 20, 5, 5], yellow), 0.0); // outside the frame
    }
}

/// Fraction (0..1) of pixels whose "bright text" state differs between `template` and the region of
/// `frame` at (x, y), searched ±`search` px. A pixel is text when all three channels are >= `thr`.
/// Unlike `template_diff`, this ignores what is behind semi-transparent text.
pub fn text_mask_diff_search(frame: &RgbImage, template: &RgbImage, x: u32, y: u32, search: u32, thr: u8) -> f64 {
    let (tw, th) = template.dimensions();
    let is_text = |p: &image::Rgb<u8>| p[0] >= thr && p[1] >= thr && p[2] >= thr;
    let s = search as i64;
    let mut best = 1.0f64;
    for dy in -s..=s {
        for dx in -s..=s {
            let (ox, oy) = (x as i64 + dx, y as i64 + dy);
            if ox < 0 || oy < 0 || ox as u32 + tw > frame.width() || oy as u32 + th > frame.height() {
                continue;
            }
            let mut mismatch = 0u64;
            for ty in 0..th {
                for tx in 0..tw {
                    let a = is_text(frame.get_pixel(ox as u32 + tx, oy as u32 + ty));
                    let b = is_text(template.get_pixel(tx, ty));
                    mismatch += (a != b) as u64;
                }
            }
            best = best.min(mismatch as f64 / (tw as f64 * th as f64));
        }
    }
    best
}

/// Mean difference (0..1) between `template` and the same-sized region of `frame` whose
/// top-left corner is (x, y). Returns 1.0 when the region does not fit in the frame.
pub fn template_diff(frame: &RgbImage, template: &RgbImage, x: u32, y: u32) -> f64 {
    let (tw, th) = template.dimensions();
    if x + tw > frame.width() || y + th > frame.height() || tw == 0 || th == 0 {
        return 1.0;
    }
    let mut sum: u64 = 0;
    for ty in 0..th {
        for tx in 0..tw {
            let a = frame.get_pixel(x + tx, y + ty);
            let b = template.get_pixel(tx, ty);
            for c in 0..3 {
                sum += (a[c] as i32 - b[c] as i32).unsigned_abs() as u64;
            }
        }
    }
    sum as f64 / (tw as f64 * th as f64 * 3.0 * 255.0)
}

/// Smallest `template_diff` with the template's top-left within ±`search` px of (x, y).
pub fn template_diff_search(frame: &RgbImage, template: &RgbImage, x: u32, y: u32, search: u32) -> f64 {
    let s = search as i64;
    let mut best = 1.0f64;
    for dy in -s..=s {
        for dx in -s..=s {
            let (cx, cy) = (x as i64 + dx, y as i64 + dy);
            if cx < 0 || cy < 0 {
                continue;
            }
            best = best.min(template_diff(frame, template, cx as u32, cy as u32));
        }
    }
    best
}

/// True when the mean luminance of `roi` falls below `threshold`: GC4 dims the HUD behind
/// event dialogs, reports and choice popups, so the normally bright top bar goes dark.
pub fn is_modal_dimmed_in(jpeg_bytes: &[u8], roi: Roi, threshold: f64) -> Result<bool> {
    let img = decode_rgb(jpeg_bytes)?;
    Ok(region_mean_luminance(&img, roi) < threshold)
}

/// `is_modal_dimmed_in` over `DEFAULT_MODAL_ROI`.
pub fn is_modal_dimmed(jpeg_bytes: &[u8], threshold: f64) -> Result<bool> {
    is_modal_dimmed_in(jpeg_bytes, DEFAULT_MODAL_ROI, threshold)
}

/// Crops a sub-region [x, y, w, h] from a JPEG and re-encodes as JPEG.
pub fn crop_region(jpeg_bytes: &[u8], x: u32, y: u32, w: u32, h: u32, quality: u8) -> Result<Vec<u8>> {
    let mut img = decode_rgb(jpeg_bytes)?;
    let iw = img.width();
    let ih = img.height();
    let crop_w = w.min(iw.saturating_sub(x));
    let crop_h = h.min(ih.saturating_sub(y));
    let cropped = imageops::crop(&mut img, x, y, crop_w, crop_h).to_image();
    encode_jpeg(&cropped, quality)
}

/// Draws an outline rectangle [x, y, w, h] over a JPEG image.
pub fn highlight_region(
    jpeg_bytes: &[u8],
    rect: [u32; 4],
    outline_rgb: [u8; 3],
    border_w: u32,
    quality: u8,
) -> Result<Vec<u8>> {
    let mut img = decode_rgb(jpeg_bytes)?;
    let [rx, ry, rw, rh] = rect;
    let max_x = (rx + rw).min(img.width());
    let max_y = (ry + rh).min(img.height());
    let color = Rgb(outline_rgb);

    for b in 0..border_w {
        // Horizontal top & bottom
        let y_top = (ry + b).min(max_y.saturating_sub(1));
        let y_bot = max_y.saturating_sub(1 + b).max(ry);
        for x in rx..max_x {
            img.put_pixel(x, y_top, color);
            img.put_pixel(x, y_bot, color);
        }
        // Vertical left & right
        let x_left = (rx + b).min(max_x.saturating_sub(1));
        let x_right = max_x.saturating_sub(1 + b).max(rx);
        for y in ry..max_y {
            img.put_pixel(x_left, y, color);
            img.put_pixel(x_right, y, color);
        }
    }

    encode_jpeg(&img, quality)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_view_to_screen_math() {
        let v = View::new(0, 0, 1.25, 1568, 882);
        let (sx, sy) = v.to_screen(100.0, 200.0).expect("In-bounds coordinates");
        assert_eq!(sx, 125);
        assert_eq!(sy, 250);

        // Out of bounds check
        assert!(v.to_screen(2000.0, 100.0).is_err());
        assert!(v.to_screen(-5.0, 100.0).is_err());
    }

    #[test]
    fn test_view_rect_to_screen() {
        let v = View::new(10, 20, 2.0, 100, 100);
        let (rx, ry, rw, rh) = v.rect_to_screen(10.0, 15.0, 20.0, 30.0);
        assert_eq!(rx, 30);
        assert_eq!(ry, 50);
        assert_eq!(rw, 40);
        assert_eq!(rh, 60);
    }

    #[test]
    fn test_jpeg_encode_decode_roundtrip() {
        let mut img = RgbImage::new(64, 64);
        for p in img.pixels_mut() {
            *p = Rgb([120, 150, 180]);
        }
        let jpeg = encode_jpeg(&img, 85).expect("JPEG encode failed");
        assert!(!jpeg.is_empty());

        let decoded = decode_rgb(&jpeg).expect("JPEG decode failed");
        assert_eq!(decoded.dimensions(), (64, 64));
    }

    #[test]
    fn test_detect_change_bbox() {
        let mut img1 = RgbImage::new(100, 100);
        for p in img1.pixels_mut() {
            *p = Rgb([10, 10, 10]);
        }
        let mut img2 = img1.clone();
        for x in 40..60 {
            for y in 30..50 {
                img2.put_pixel(x, y, Rgb([200, 200, 200]));
            }
        }

        let j1 = encode_jpeg(&img1, 95).unwrap();
        let j2 = encode_jpeg(&img2, 95).unwrap();

        let bbox = detect_change_bbox(&j1, &j2, 30, 2).expect("BBox detection").expect("Should detect changes");
        let [bx, by, bw, bh] = bbox;
        assert!(bx <= 40);
        assert!(by <= 30);
        assert!(bx + bw >= 60);
        assert!(by + bh >= 50);
    }

    #[test]
    fn roi_from_norm_maps_and_clamps() {
        assert_eq!(roi_from_norm(1568, 882, [0.948, 0.004, 0.05, 0.028]), [1486, 4, 78, 25]);
        assert_eq!(roi_from_norm(100, 100, [0.9, 0.9, 0.5, 0.5]), [90, 90, 10, 10], "clamped to the image");
        assert_eq!(roi_from_norm(100, 100, [2.0, 2.0, 0.0, 0.0]), [99, 99, 1, 1]);
    }

    #[test]
    fn region_diff_is_zero_for_identical_and_large_for_changed_text() {
        let mut a = RgbImage::new(200, 100);
        for p in a.pixels_mut() {
            *p = Rgb([40, 40, 60]);
        }
        let mut b = a.clone();
        for y in 10..20 {
            for x in 150..190 {
                b.put_pixel(x, y, Rgb([230, 230, 230])); // "text" appears in the top-right box
            }
        }
        let roi = [140, 5, 55, 25];
        assert_eq!(region_diff(&a, &a, roi), 0.0);
        assert!(region_diff(&a, &b, roi) > 0.1, "{}", region_diff(&a, &b, roi));
        assert_eq!(region_diff(&a, &b, [0, 50, 100, 40]), 0.0, "changes outside the roi do not count");
        assert!((region_mean_luminance(&a, roi) - 42.28).abs() < 0.5);
    }

    #[test]
    fn max_strip_catches_a_single_changed_glyph_that_the_mean_misses() {
        let bg = Rgb([20, 30, 50]);
        let mut a = RgbImage::from_pixel(78, 25, bg);
        // twelve "glyphs", 5 px wide with 1 px gaps
        for g in 0..12 {
            for y in 6..19 {
                for x in (g * 6 + 1)..(g * 6 + 5) {
                    a.put_pixel(x, y, Rgb([120, 170, 230]));
                }
            }
        }
        let mut b = a.clone();
        for y in 6..19 {
            for x in 13..17 {
                b.put_pixel(x, y, bg); // one glyph changes shape
            }
        }
        let roi = [0, 0, 78, 25];
        assert!(region_diff(&a, &b, roi) < 0.03, "whole-box mean misses it: {}", region_diff(&a, &b, roi));
        assert!(region_diff_max_strip(&a, &b, roi, 6) > 0.1, "{}", region_diff_max_strip(&a, &b, roi, 6));
        assert_eq!(region_diff_max_strip(&a, &a, roi, 6), 0.0);
    }

    #[test]
    fn max_strip_on_real_gc4_date_readouts() {
        // 92x36 crops of the top-right date readout from live 1568x882 frames.
        let load = |name: &str| {
            let path = format!("{}/tests/fixtures/{}", env!("CARGO_MANIFEST_DIR"), name);
            decode_rgb(&std::fs::read(path).unwrap()).unwrap()
        };
        let apr_a = load("date_apr2_a.jpg");
        let roi = [10, 4, 78, 25]; // turn_indicator_roi relative to the crop origin (1476, 0)
        let same = region_diff_max_strip(&apr_a, &load("date_apr2_b.jpg"), roi, 6);
        assert!(same < 0.01, "same date must read as unchanged: {same}");
        for other in ["date_aug2.jpg", "date_mar14.jpg"] {
            let changed = region_diff_max_strip(&apr_a, &load(other), roi, 6);
            assert!(changed > 0.06, "Apr 2 vs {other} must read as changed: {changed}");
        }
    }

    #[test]
    fn template_diff_matches_real_gnn_logo_and_rejects_the_map() {
        let fixture = |name: &str| {
            let path = format!("{}/tests/fixtures/{}", env!("CARGO_MANIFEST_DIR"), name);
            decode_rgb(&std::fs::read(path).unwrap()).unwrap()
        };
        let tpl_path = format!("{}/../../corpora/galciv4/templates/gnn_live.png", env!("CARGO_MANIFEST_DIR"));
        let tpl = image::open(tpl_path).unwrap().to_rgb8();
        // fixtures are crops starting at (290, 626); the template sits at (300, 636)
        let hit = template_diff(&fixture("gnn_region.jpg"), &tpl, 10, 10);
        let miss = template_diff(&fixture("map_region.jpg"), &tpl, 10, 10);
        assert!(hit < 0.03, "GNN bulletin must match its template: {hit}");
        assert!(miss > 0.15, "ordinary map must not match: {miss}");
        assert_eq!(template_diff(&tpl, &tpl, 0, 0), 0.0);
        assert_eq!(template_diff(&tpl, &tpl, 1, 0), 1.0, "out of bounds never matches");
    }

    #[test]
    fn template_search_matches_a_one_pixel_shifted_centered_title() {
        let fixture = |name: &str| {
            let path = format!("{}/tests/fixtures/{}", env!("CARGO_MANIFEST_DIR"), name);
            decode_rgb(&std::fs::read(path).unwrap()).unwrap()
        };
        let tpl_path = format!("{}/../../corpora/galciv4/templates/boarding_title.png", env!("CARGO_MANIFEST_DIR"));
        let tpl = image::open(tpl_path).unwrap().to_rgb8();
        // live frame from Colony Ship-4, cropped at (594, 235); the manifest ROI is (604, 245)
        let region = fixture("boarding_ship4_region.jpg");
        let fixed = template_diff(&region, &tpl, 10, 10);
        let searched = template_diff_search(&region, &tpl, 10, 10, 2);
        assert!(fixed > 0.08, "fixed position misses the shifted title: {fixed}");
        assert!(searched < 0.06, "±2 px search finds it: {searched}");
    }

    #[test]
    fn test_modal_dimmed_luminance() {
        let mut bright = RgbImage::new(600, 50);
        for p in bright.pixels_mut() {
            *p = Rgb([150, 150, 150]); // lum ~150
        }
        let bright_jpg = encode_jpeg(&bright, 85).unwrap();
        assert!(!is_modal_dimmed(&bright_jpg, 22.0).unwrap());

        let mut dim = RgbImage::new(600, 50);
        for p in dim.pixels_mut() {
            *p = Rgb([10, 10, 10]); // lum ~10
        }
        let dim_jpg = encode_jpeg(&dim, 85).unwrap();
        assert!(is_modal_dimmed(&dim_jpg, 22.0).unwrap());
    }

    #[test]
    fn test_crop_and_highlight() {
        let img = RgbImage::new(100, 100);
        let orig_jpg = encode_jpeg(&img, 85).unwrap();

        let cropped = crop_region(&orig_jpg, 10, 10, 20, 20, 85).expect("Crop region");
        let dec_crop = decode_rgb(&cropped).unwrap();
        assert_eq!(dec_crop.dimensions(), (20, 20));

        let highlighted = highlight_region(&orig_jpg, [10, 10, 30, 30], [255, 0, 0], 2, 85).expect("Highlight");
        assert!(!highlighted.is_empty());
    }
}
