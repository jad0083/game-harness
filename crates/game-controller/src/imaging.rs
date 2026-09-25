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
