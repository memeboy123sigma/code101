import time
from machine import ADC, Pin

# Pin Configuration
JOY_VRX_PIN = 26  # GP26 (ADC0)
JOY_VRY_PIN = 27  # GP27 (ADC1)
JOY_SW_PIN = 22  # GP22

# Initialize Analog & Digital Inputs
joy_vrx = ADC(Pin(JOY_VRX_PIN))
joy_vry = ADC(Pin(JOY_VRY_PIN))
joy_sw = Pin(JOY_SW_PIN, Pin.IN, Pin.PULL_UP)

print("=== Joystick Center Calibration ===")
print("Please leave the joystick completely untouched...")
time.sleep(1)

# Capture resting position as the baseline center
CENTER_X = joy_vrx.read_u16()
CENTER_Y = joy_vry.read_u16()

print(f"Calibration Complete!")
print(f"Found Center X: {CENTER_X}")
print(f"Found Center Y: {CENTER_Y}\n")

# Deadzone threshold (adjust if it's too sensitive or not sensitive enough)
DEADZONE = 4000

print("Starting live test loop...\n")

while True:
    # Read current raw values
    x_val = joy_vrx.read_u16()
    y_val = joy_vry.read_u16()
    is_pressed = joy_sw.value() == 0

    # Calculate difference from the discovered center
    x_diff = x_val - CENTER_X
    y_diff = y_val - CENTER_Y

    # Determine direction using the calibrated center and deadzone
    direction = "CENTER"
    if abs(x_diff) > DEADZONE or abs(y_diff) > DEADZONE:
        if abs(x_diff) > abs(y_diff):
            direction = "LEFT" if x_diff < 0 else "RIGHT"
        else:
            direction = "UP" if y_diff < 0 else "DOWN"

    button_str = "PRESSED" if is_pressed else "RELEASED"

    # Display live output
    print(
        f"X: {x_val:5d} (Diff: {x_diff:6d}) | Y: {y_val:5d} (Diff: {y_diff:6d}) | Dir: {direction:6s} | Button: {button_str}"
    )

    time.sleep(0.1)
