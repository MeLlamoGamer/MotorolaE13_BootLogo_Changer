#!/usr/bin/env python3
"""
logotool.py - desempaqueta / empaqueta el logo.bin del Motorola Moto E13.

Formato (deducido del logo.bin original, ver explicacion):

    0x00  'G' 'Z'            magic
    0x02  u16 LE             cantidad de imagenes (N, en tu archivo = 4)
    0x04  ...                ceros (relleno hasta la tabla de tamanos)
    0x28-4*N  u32 LE * N     tamano en bytes de cada stream gzip
    0x28  gzip #1, gzip #2, ... pegados uno tras otro, sin padding

    Cada gzip contiene un BMP crudo (header de 54 bytes, 720x1600,
    bottom-up, sin compresion; 24bpp o 32bpp segun la imagen).

Uso:
    python3 logotool.py info    logo.bin
    python3 logotool.py unpack  logo.bin carpeta/
    python3 logotool.py pack    carpeta/ nuevo_logo.bin [--resize]
    python3 logotool.py verify  logo.bin      (unpack + pack == original?)

Solo usa la libreria estandar. Pillow es OPCIONAL: se necesita solo si
queres meter PNG/JPG, o BMPs "raros" (los que exporta GIMP/Paint, etc).
"""
import argparse
import json
import os
import struct
import sys
import zlib

MAGIC = b"GZ"
DATA_START = 0x28
BMP_HDR = 54


# ----------------------------------------------------------------- gzip ----
def gzip_parse_header(chunk):
    """Devuelve (nombre, mtime, xfl, os, offset_donde_empieza_deflate)."""
    if chunk[:3] != b"\x1f\x8b\x08":
        raise ValueError("no es un stream gzip (deflate)")
    flg = chunk[3]
    if flg & ~0x08:
        raise ValueError(f"flags gzip no soportados: {flg:#x}")
    mtime = struct.unpack("<I", chunk[4:8])[0]
    xfl, osb = chunk[8], chunk[9]
    pos = 10
    name = b""
    if flg & 0x08:
        end = chunk.index(b"\0", pos)
        name = chunk[pos:end]
        pos = end + 1
    return name.decode("latin-1"), mtime, xfl, osb, pos


def gzip_decompress(chunk):
    name, mtime, xfl, osb, pos = gzip_parse_header(chunk)
    d = zlib.decompressobj(-15)
    raw = d.decompress(chunk[pos:])
    trailer = d.unused_data
    crc, isize = struct.unpack("<II", trailer[:8])
    if crc != zlib.crc32(raw) or isize != len(raw) & 0xFFFFFFFF:
        raise ValueError("CRC/tamano del gzip no coinciden")
    return raw, dict(name=name, mtime=mtime, xfl=xfl, os=osb)


def gzip_compress(raw, name, mtime, xfl=2, osb=0xFF):
    """gzip nivel 9 armado a mano (reproduce byte a byte el original)."""
    hdr = b"\x1f\x8b\x08\x08" + struct.pack("<I", mtime) + bytes([xfl, osb])
    hdr += name.encode("latin-1") + b"\0"
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = c.compress(raw) + c.flush()
    return hdr + body + struct.pack("<II", zlib.crc32(raw), len(raw) & 0xFFFFFFFF)


# ------------------------------------------------------------------ bmp ----
def bmp_info(b):
    if len(b) < BMP_HDR or b[:2] != b"BM":
        raise ValueError("no es un BMP")
    fsize, _, _, off = struct.unpack("<IHHI", b[2:14])
    hsz, w, h, planes, bpp, comp, isz = struct.unpack("<IiiHHII", b[14:38])
    return dict(fsize=fsize, off=off, hsz=hsz, w=w, h=h, planes=planes,
                bpp=bpp, comp=comp, isz=isz)


def bmp_is_canonical(b, w, h, bpp):
    """True si el BMP es identico en estructura al que usa el logo.bin."""
    try:
        i = bmp_info(b)
    except ValueError:
        return False
    stride = ((w * bpp + 31) // 32) * 4
    return (i["hsz"] == 40 and i["off"] == BMP_HDR and i["w"] == w
            and i["h"] == h and i["planes"] == 1 and i["bpp"] == bpp
            and i["comp"] == 0 and i["fsize"] == len(b)
            and len(b) == BMP_HDR + stride * h)


def bmp_build(pixels_bottom_up, w, h, bpp):
    size = BMP_HDR + len(pixels_bottom_up)
    hdr = b"BM" + struct.pack("<IHHI", size, 0, 0, BMP_HDR)
    hdr += struct.pack("<IiiHHIIiiII", 40, w, h, 1, bpp, 0,
                       len(pixels_bottom_up), 0, 0, 0, 0)
    return hdr + pixels_bottom_up


def image_to_bmp(path, w, h, bpp, resize=False):
    """Convierte cualquier imagen (via Pillow) al BMP canonico w*h*bpp."""
    try:
        from PIL import Image
    except ImportError:
        sys.exit(f"'{path}' no es un BMP canonico y no tengo Pillow para "
                 f"convertirlo.  pip install pillow")
    im = Image.open(path)
    if im.size != (w, h):
        if not resize:
            sys.exit(f"'{path}' mide {im.size[0]}x{im.size[1]} y se espera "
                     f"{w}x{h}. Usa --resize para escalar (se deforma).")
        im = im.convert("RGB").resize((w, h), Image.LANCZOS)
    # el alpha (si hay) se descarta: en 32bpp queda fijo en 255 (opaco)
    im = im.convert("RGB").transpose(Image.FLIP_TOP_BOTTOM)
    if bpp == 24:
        raw = im.tobytes("raw", "BGR")
    elif bpp == 32:
        raw = Image.merge("RGBA", (*im.split(), Image.new("L", im.size, 255))
                          ).tobytes("raw", "BGRA")
    else:
        sys.exit(f"bpp {bpp} no soportado")
    stride = ((w * bpp + 31) // 32) * 4
    rowlen = w * bpp // 8
    if stride != rowlen:  # padding de fila (no ocurre con 720px)
        raw = b"".join(raw[r * rowlen:(r + 1) * rowlen].ljust(stride, b"\0")
                       for r in range(h))
    return bmp_build(raw, w, h, bpp)


# ---------------------------------------------------------- contenedor ----
def parse(data):
    if data[:2] != MAGIC:
        raise ValueError("magic != 'GZ': no parece un logo.bin de este tipo")
    n = struct.unpack("<H", data[2:4])[0]
    if not 1 <= n <= 9:
        raise ValueError(f"cantidad de imagenes rara: {n}")
    tab = DATA_START - 4 * n
    sizes = list(struct.unpack(f"<{n}I", data[tab:DATA_START]))
    if DATA_START + sum(sizes) != len(data):
        raise ValueError("la tabla de tamanos no cuadra con el tamano del "
                         "archivo (formato distinto al deducido)")
    return n, tab, sizes


def cmd_info(args):
    data = open(args.logo, "rb").read()
    n, tab, sizes = parse(data)
    print(f"archivo: {len(data)} bytes | imagenes: {n} | tabla de tamanos en {tab:#x}")
    off = DATA_START
    for i, s in enumerate(sizes, 1):
        raw, g = gzip_decompress(data[off:off + s])
        b = bmp_info(raw)
        print(f" #{i}: offset {off:#08x}  gzip {s:>8} B  ->  bmp {len(raw):>8} B "
              f"({b['w']}x{b['h']} {b['bpp']}bpp)  name={g['name']!r} "
              f"mtime={g['mtime']}")
        off += s


def cmd_unpack(args):
    data = open(args.logo, "rb").read()
    n, tab, sizes = parse(data)
    os.makedirs(args.dir, exist_ok=True)
    entries, off = [], DATA_START
    for i, s in enumerate(sizes, 1):
        raw, g = gzip_decompress(data[off:off + s])
        b = bmp_info(raw)
        open(os.path.join(args.dir, f"{i}.bmp"), "wb").write(raw)
        entries.append(dict(g, w=b["w"], h=b["h"], bpp=b["bpp"]))
        off += s
    manifest = dict(count=n, header_hex=data[:tab].hex(), entries=entries)
    json.dump(manifest, open(os.path.join(args.dir, "manifest.json"), "w"), indent=2)
    print(f"{n} imagenes extraidas en {args.dir}/ (+ manifest.json)")


def build(dirpath, resize=False):
    man = json.load(open(os.path.join(dirpath, "manifest.json")))
    n = man["count"]
    header = bytearray.fromhex(man["header_hex"])
    chunks = []
    for i, e in enumerate(man["entries"], 1):
        bmp_path = os.path.join(dirpath, f"{i}.bmp")
        png_path = os.path.join(dirpath, f"{i}.png")
        path = bmp_path if os.path.exists(bmp_path) else png_path
        if not os.path.exists(path):
            sys.exit(f"falta {i}.bmp (o {i}.png) en {dirpath}")
        b = open(path, "rb").read()
        if not (path.endswith(".bmp") and bmp_is_canonical(b, e["w"], e["h"], e["bpp"])):
            print(f" #{i}: {os.path.basename(path)} se convierte a BMP "
                  f"{e['w']}x{e['h']} {e['bpp']}bpp")
            b = image_to_bmp(path, e["w"], e["h"], e["bpp"], resize)
        chunks.append(gzip_compress(b, e["name"], e["mtime"], e["xfl"], e["os"]))
    out = bytes(header) + b"".join(struct.pack("<I", len(c)) for c in chunks)
    assert len(out) == DATA_START
    return out + b"".join(chunks), n


def cmd_pack(args):
    out, n = build(args.dir, args.resize)
    open(args.out, "wb").write(out)
    print(f"{args.out}: {len(out)} bytes, {n} imagenes")
    print("OJO: verifica que no supere el tamano de tu particion 'logo'.")


def cmd_verify(args):
    import tempfile
    orig = open(args.logo, "rb").read()
    with tempfile.TemporaryDirectory() as t:
        class A: pass
        a = A(); a.logo = args.logo; a.dir = t
        cmd_unpack(a)
        out, _ = build(t)
    print("OK: repack identico byte a byte" if out == orig
          else f"DIFIERE (orig {len(orig)} B, repack {len(out)} B)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("info");   s.add_argument("logo");  s.set_defaults(f=cmd_info)
    s = sp.add_parser("unpack"); s.add_argument("logo"); s.add_argument("dir"); s.set_defaults(f=cmd_unpack)
    s = sp.add_parser("pack");   s.add_argument("dir"); s.add_argument("out")
    s.add_argument("--resize", action="store_true"); s.set_defaults(f=cmd_pack)
    s = sp.add_parser("verify"); s.add_argument("logo"); s.set_defaults(f=cmd_verify)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
