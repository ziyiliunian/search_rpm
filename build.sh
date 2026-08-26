#!/bin/bash
set -e
cd "$(dirname "$0")"
APP_NAME="kylin-server-rpm-search"
VERSION="${1:-1.0.0}"
OUT_DIR="dist"
mkdir -p build
PKGROOT=$(mktemp -d "build/pkgroot.${VERSION}.XXXXXX")
trap 'find "$PKGROOT" -depth -delete 2>/dev/null || true' EXIT
mkdir -p "$PKGROOT/DEBIAN" "$PKGROOT/opt/$APP_NAME" "$PKGROOT/usr"
cp -r src "$PKGROOT/opt/$APP_NAME/"
find "$PKGROOT/opt/$APP_NAME" -type f -name '*.py[co]' -delete
find "$PKGROOT/opt/$APP_NAME" -depth -type d -name __pycache__ -delete
cp packaging/DEBIAN/control "$PKGROOT/DEBIAN/control"
cp packaging/DEBIAN/postinst "$PKGROOT/DEBIAN/postinst"
cp packaging/DEBIAN/postrm "$PKGROOT/DEBIAN/postrm"
cp -r packaging/usr/* "$PKGROOT/usr/"
sed -i "s/^Version:.*/Version: ${VERSION}/" "$PKGROOT/DEBIAN/control"
SIZE_KB=$(du -sk "$PKGROOT/opt" "$PKGROOT/usr" | awk '{s+=$1} END {print s}')
sed -i "s/^Installed-Size:.*/Installed-Size: ${SIZE_KB}/" "$PKGROOT/DEBIAN/control"
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/postrm" "$PKGROOT/usr/bin/$APP_NAME"
mkdir -p "$OUT_DIR"
dpkg-deb --build --root-owner-group "$PKGROOT" "$OUT_DIR/${APP_NAME}_${VERSION}_all.deb"
echo "构建完成：$OUT_DIR/${APP_NAME}_${VERSION}_all.deb"
