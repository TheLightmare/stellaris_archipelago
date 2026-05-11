#pragma once

bool bridge_start();
void bridge_stop();
int bridge_tick();

// Implemented in dllmain.cpp. Marshals a queue flush onto the game thread
// via SendMessage so Phase 2 engine calls run in the correct thread context.
// Returns the number of commands flushed, or -1 if the game window hasn't
// been hooked yet.
int dispatch_flush_on_game_thread();
