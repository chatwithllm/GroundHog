TARGET  = sp5fw
CC      = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
SIZE    = arm-none-eabi-size

CFLAGS  = -mcpu=cortex-m3 -mthumb -Os -g -Wall -Wextra \
          -ffreestanding -fno-common -ffunction-sections -fdata-sections
LDFLAGS = -T linker.ld -nostdlib -Wl,--gc-sections -Wl,-Map=$(TARGET).map

SRCS = startup.c main.c smbus.c

all: $(TARGET).bin

$(TARGET).elf: $(SRCS) linker.ld
	$(CC) $(CFLAGS) $(LDFLAGS) $(SRCS) -o $@
	$(SIZE) $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -f $(TARGET).elf $(TARGET).bin $(TARGET).map

.PHONY: all clean
