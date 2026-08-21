
ARCH=

.PHONY: all image bindist clean lint

all: image

image:
	$(MAKE) -C build image

lint:
	pyflakes build/*.py

clean:
	$(MAKE) -C build clean

bindist:
	$(MAKE) -C build bindist
