use minifb::{Key, MouseButton, MouseMode, Window, WindowOptions};
use minifb_fonts::{font5x8, font6x8};

use crate::stars::{fetch_catalog, load_catalog};

const WIDTH: usize = 800;
const HEIGHT: usize = 800;

mod stars;

fn main() {
    let catalog_path = String::from("../data/stars");
    fetch_catalog(&catalog_path); //ensure that the star catalog is downloaded
    let stars = load_catalog(&catalog_path, 200.0);

    let mut buffer: Vec<u32> = vec![0; WIDTH * HEIGHT];

    let mut window = Window::new("Star Map", WIDTH, HEIGHT, WindowOptions::default())
        .expect("Failed to create window");

    window.set_target_fps(60);

    let mut last_mouse: Option<(f32, f32)> = None;

    while window.is_open() && !window.is_key_down(Key::Escape) {
        let mouse_pos = window.get_mouse_pos(MouseMode::Discard);
        if window.get_mouse_down(MouseButton::Left) {
            if let (Some(current), Some(last)) = (mouse_pos, last_mouse) {
                let _dx = current.0 - last.0;
                let _dy = current.1 - last.1;
            }
            last_mouse = mouse_pos;
        } else {
            last_mouse = None;
        }

        //reset frame to black
        buffer.fill(0x00_00_00_00);

        if (window.is_key_down(Key::D)) {
            draw_scaled_text(&mut buffer, WIDTH, 100, 100, "mouse down", 0xFF_FF_FF_FF, 2);
        }

        draw_pixel(&mut buffer, WIDTH / 2, HEIGHT / 2, 0xFF_FF_FF_FF);

        window.update_with_buffer(&buffer, WIDTH, HEIGHT).unwrap();
    }
}

fn draw_pixel(buffer: &mut Vec<u32>, x: usize, y: usize, color: u32) {
    if x < WIDTH && y < HEIGHT {
        buffer[y * WIDTH + x] = color;
    }
}

fn draw_scaled_text(
    buffer: &mut [u32],
    width: usize,
    x: usize,
    y: usize,
    text: &str,
    color: u32,
    scale: usize,
) {
    // render into a small temp buffer sized to fit the text
    let text_w = text.len() * 6;
    let text_h = 8;
    let mut temp = vec![0u32; text_w * text_h];

    let text_renderer = minifb_fonts::font6x8::new_renderer(text_w, text_h, color);
    text_renderer.draw_text(&mut temp, 0, 0, text);

    // blit temp into main buffer, scaling each pixel up
    for ty in 0..text_h {
        for tx in 0..text_w {
            let px = temp[ty * text_w + tx];
            if px != 0 {
                for sy in 0..scale {
                    for sx in 0..scale {
                        let dx = x + tx * scale + sx;
                        let dy = y + ty * scale + sy;
                        if dx < width {
                            buffer[dy * width + dx] = px;
                        }
                    }
                }
            }
        }
    }
}
