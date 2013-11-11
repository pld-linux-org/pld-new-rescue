
.PHONY: cd usb bindist clean

all: usb cd

cd:
	$(MAKE) -C build cd

usb:
	$(MAKE) -C build cd

clean:
	$(MAKE) -C build clean

bindist:
	$(MAKE) -C build bindist
