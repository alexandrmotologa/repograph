pub struct Engine {
    pub power: u32,
}

impl Engine {
    pub fn new(power: u32) -> Self {
        Self { power }
    }

    pub fn compute(&self) -> bool {
        self.power > 0
    }
}
