#pragma once

#include <Arduino.h>

namespace weatherService {

struct Weather {
  bool valid;
  char shortDesc[32];
  float tempNow;
};

void begin();
void update(const char* desc, float temp);
bool isValid();
const Weather& current();

} // namespace weatherService
