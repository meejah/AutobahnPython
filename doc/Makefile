all:
	@echo "Targets:"
	@echo ""
	@echo "  clean             : cleanup build artifacts"
	@echo "  test              : build everything and run locally"
	@echo "  test_no_network   : build everything for no network access and run locally"
	@echo "  publish           : build everything and publish to S3"
	@echo "  copy              : copy over shared files to other AutobahnXXX repos"
	@echo "  install_deps      : install build dependencies"
	@echo "  spelling          : run spell checking"
	@echo "  doctest           : run doctests"
	@echo ""

# XXX
# I can't make SCons play nicely with a virtualenv -- it won't install
# in one, and when I do a sphinx-build inside one via "python `which
# scons`" the trollius imports fail (but inside the same venv,
# sphinx-build works fine). So, I'm giving up on SCons since we don't
# actually optimize any SVGs with it so all it's doing is the "upload
# to Amazon S3" step which I can't test anyway...

venv: Makefile requirements.txt
	scons --version > /dev/null # make sure we have SCons
	virtualenv --system-site-packages ./venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	./venv/bin/pip install --editable ../[asyncio,twisted]

build: venv
	./venv/bin/sphinx-build -A cstatic="//tavendo-common-static.s3-eu-west-1.amazonaws.com" -b html . _build

__build:
	scons

build_no_network:
	scons --no_network

test: build
	python serve.py --root ./_build --silence

test_no_network: build_no_network
	python serve.py --root ./_build --silence

clean:
	rm -rf _build
	rm -rf _build_uploaded
	rm -rf _static/img/gen
	rm -rf _test
	rm -rf _spelling

publish: clean build
	scons publish

doctest:
	PYTHONPATH=../autobahn sphinx-build -b doctest -v . _test

copy_makefile:
	cp Makefile ../../AutobahnJS/doc/
	cp Makefile ../../AutobahnAndroid/doc/
	cp Makefile ../../AutobahnCpp/doc/
	cp Makefile ../../AutobahnTestsuite/doc/

copy_gitignore:
	cp .gitignore ../../AutobahnJS/doc/
	cp .gitignore ../../AutobahnAndroid/doc/
	cp .gitignore ../../AutobahnCpp/doc/
	cp .gitignore ../../AutobahnTestsuite/doc/

copy_serve:
	cp serve.py ../../AutobahnJS/doc/
	cp serve.py ../../AutobahnAndroid/doc/
	cp serve.py ../../AutobahnCpp/doc/
	cp serve.py ../../AutobahnTestsuite/doc/

copy_wordlist:
	cp spelling_wordlist.txt ../../AutobahnJS/doc/
	cp spelling_wordlist.txt ../../AutobahnAndroid/doc/
	cp spelling_wordlist.txt ../../AutobahnCpp/doc/
	cp spelling_wordlist.txt ../../AutobahnTestsuite/doc/

# copy_readme:
# 	cp README.md ../../AutobahnJS/doc/
# 	cp README.md ../../AutobahnAndroid/doc/
# 	cp README.md ../../AutobahnCpp/doc/
# 	cp README.md ../../AutobahnTestsuite/doc/

copy: copy_makefile copy_gitignore copy_serve

install_deps:
	pip install -U scour
	pip install -U taschenmesser
	#pip install -U scons
	pip install -U sphinx
	pip install -U sphinx-bootstrap-theme
	pip install -U pyenchant
	pip install -U sphinxcontrib-spelling
	pip install -U repoze.sphinx.autointerface

spelling:
	PYTHONPATH=../autobahn sphinx-build -b spelling . _spelling
