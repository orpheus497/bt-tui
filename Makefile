# Makefile for FreeBSD Bluetooth TUI Manager

PREFIX?= /usr/local
RCDIR?= $(PREFIX)/etc/rc.d
PYTHON?= python3
SETUP_PY= setup.py
RC_SCRIPT= src/bsd_bt_daemon.rc
RC_TARGET= bsd_bt_daemon

.PHONY: all install uninstall clean test

all:
	@echo "Available targets:"
	@echo "  install   - Install python package and rc script"
	@echo "  uninstall - Remove python package and rc script"
	@echo "  clean     - Remove build artifacts"
	@echo "  test      - Run unit tests"

install:
	@echo "Installing Python package..."
	$(PYTHON) $(SETUP_PY) install --prefix=$(PREFIX) --record install_files.txt
	@echo "Installing rc.d script..."
	install -m 755 $(RC_SCRIPT) $(RCDIR)/$(RC_TARGET)
	@echo "========================================================"
	@echo "Installation complete."
	@echo "To enable the service, run:"
	@echo "  sysrc bsd_bt_daemon_enable=\"YES\""
	@echo "  service bsd_bt_daemon start"
	@echo "========================================================"

uninstall:
	@echo "Removing rc.d script..."
	rm -f $(RCDIR)/$(RC_TARGET)
	@echo "Removing Python package..."
	@if [ -f install_files.txt ]; then \
		while IFS= read -r file; do \
			[ -n "$$file" ] && rm -rf -- "$$file"; \
		done < install_files.txt; \
		rm install_files.txt; \
	else \
		echo "Warning: install_files.txt not found. Pip uninstall recommended."; \
	fi
	@echo "Uninstall complete."

clean:
	rm -rf build dist src/*.egg-info __pycache__ src/__pycache__ tests/__pycache__ install_files.txt

test:
	$(PYTHON) -m unittest discover tests
