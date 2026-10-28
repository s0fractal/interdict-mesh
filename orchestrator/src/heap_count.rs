//! Test builds only: the heap bytes the current thread holds, for the measurements of what the
//! block table's bounded collections cost per entry (`measure_memory_at_bounds`, ADR-0013).
//! Counts requested sizes, not the allocator's own overhead: RSS on a host adds that.
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

pub struct Counting;

thread_local! {
    static LIVE: Cell<i64> = const { Cell::new(0) };
}

fn add(bytes: i64) {
    // During thread teardown the slot may be gone; such bytes are not measured.
    let _ = LIVE.try_with(|live| live.set(live.get() + bytes));
}

// SAFETY: every call is passed to the system allocator unchanged; only a counter is kept.
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(layout) };
        if !p.is_null() {
            add(layout.size() as i64);
        }
        p
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(layout) };
        if !p.is_null() {
            add(layout.size() as i64);
        }
        p
    }

    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) };
        add(-(layout.size() as i64));
    }

    unsafe fn realloc(&self, p: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, layout, new_size) };
        if !q.is_null() {
            add(new_size as i64 - layout.size() as i64);
        }
        q
    }
}

/// Heap bytes this thread has allocated and not freed since it started.
pub fn live() -> i64 {
    LIVE.with(Cell::get)
}
