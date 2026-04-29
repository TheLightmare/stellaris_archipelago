#pragma once
#include <string>
#include <vector>

bool console_init();
bool console_execute_batch(const std::vector<std::string>& commands);
void console_queue_command(const std::string& command);
int console_process_queue();
bool console_is_ready();
