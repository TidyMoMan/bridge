use std::fs;

pub struct Star {
    pub name: String, // proper name, empty string if none
    pub x: f32,       // light-years from Sol
    pub y: f32,
    pub z: f32,
    pub mag: f32,  // apparent magnitude (lower = brighter)
    pub dist: f32, // light-years from Sol
}

impl Star {
    pub fn is_named(&self) -> bool {
        !self.name.is_empty()
    }
}

/// D wnload the HYG catalog CSV to a local file if it doesn't exist.
/// Call this once at startup.
pub fn fetch_catalog(path: &str) -> Result<(), Box<dyn std::error::Error>> {
    if std::path::Path::new(path).exists() {
        return Ok(());
    }

    println!("Downloading HYG catalog...");
    let url = "https://raw.githubusercontent.com/astronexus/HYG-Database/master/hyg/v3/hyg_v3.csv";
    let response = ureq::get(url).call()?.into_string()?;
    fs::write(path, response)?;
    println!("Saved to {path}");
    Ok(())
}

/// Parse the CSV and return all stars within `max_ly` light-years.
pub fn load_catalog(path: &str, max_ly: f32) -> Result<Vec<Star>, Box<dyn std::error::Error>> {
    let content = fs::read_to_string(path)?;
    let mut lines = content.lines();

    // Parse header to find column indices
    let header = lines.next().ok_or("empty file")?;
    let cols: Vec<&str> = header.split(',').collect();
    let idx = |name: &str| {
        cols.iter()
            .position(|&c| c == name)
            .ok_or_else(|| format!("column '{name}' not found"))
    };

    let i_x = idx("x")?;
    let i_y = idx("y")?;
    let i_z = idx("z")?;
    let i_mag = idx("mag")?;
    let i_dist = idx("dist")?;
    let i_proper = idx("proper")?;

    // Parsecs to light-years
    const PC_TO_LY: f32 = 3.26156;

    let mut stars = Vec::new();

    for line in lines {
        let fields: Vec<&str> = line.split(',').collect();
        if fields.len() <= i_proper {
            continue;
        }

        let x = fields[i_x].parse::<f32>().unwrap_or(0.0) * PC_TO_LY;
        let y = fields[i_y].parse::<f32>().unwrap_or(0.0) * PC_TO_LY;
        let z = fields[i_z].parse::<f32>().unwrap_or(0.0) * PC_TO_LY;
        let dist = fields[i_dist].parse::<f32>().unwrap_or(f32::MAX) * PC_TO_LY;
        let mag = fields[i_mag].parse::<f32>().unwrap_or(0.0);

        if dist > max_ly {
            continue;
        }

        stars.push(Star {
            name: fields[i_proper].trim().to_string(),
            x,
            y,
            z,
            mag,
            dist,
        });
    }

    println!("Loaded {} stars within {max_ly} ly", stars.len());
    Ok(stars)
}

// --- Query helpers ---

/// Stars sorted nearest to farthest.
pub fn by_distance(stars: &[Star]) -> Vec<&Star> {
    let mut refs: Vec<&Star> = stars.iter().collect();
    refs.sort_by(|a, b| a.dist.partial_cmp(&b.dist).unwrap());
    refs
}

/// Stars sorted brightest to dimmest (lowest mag first).
pub fn by_brightness(stars: &[Star]) -> Vec<&Star> {
    let mut refs: Vec<&Star> = stars.iter().collect();
    refs.sort_by(|a, b| a.mag.partial_cmp(&b.mag).unwrap());
    refs
}

/// Named stars only.
pub fn named(stars: &[Star]) -> Vec<&Star> {
    stars.iter().filter(|s| s.is_named()).collect()
}

/// Find a star by proper name (case-insensitive).
pub fn find_by_name<'a>(stars: &'a [Star], name: &str) -> Option<&'a Star> {
    let name = name.to_lowercase();
    stars.iter().find(|s| s.name.to_lowercase() == name)
}
