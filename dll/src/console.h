#pragma once
#include <string>
#include <vector>

bool console_init();
bool console_execute_batch(const std::vector<std::string>& commands);
void console_queue_command(const std::string& command);
int console_process_queue();
bool console_is_ready();

// Human/machine readable state for the STATUS pipe command, e.g.
//   "mode=phase2 ready=1 queued=0 executed=12 failed=0"
// mode is phase2 (direct engine call), phase1 (SendInput fallback) or none.
std::string console_status();
