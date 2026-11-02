#include "weather_service.h"
#include <string.h>

namespace weatherService {

static Weather state = {false, "", 0.0f};

void begin() {
  state.valid = false;
}

void update(const char* desc, float temp) {
  state.valid = true;
  strlcpy(state.shortDesc, desc != nullptr ? desc : "", sizeof(state.shortDesc));
  state.tempNow = temp;
}

bool isValid() {
  return state.valid;
}

const Weather& current() {
  return state;
}

} // namespace weatherService
