
.PHONY: cd usb bindist clean

all: image

image:
	$(MAKE) -C build image

clean:
	$(MAKE) -C build clean

bindist:
	$(MAKE) -C build bindist
