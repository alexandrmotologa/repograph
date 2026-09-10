mod engine;
use engine::Engine;

fn main() {
    let eng = Engine::new(500);
    eng.compute();
}
