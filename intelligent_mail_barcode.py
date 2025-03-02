#!/usr/bin/env python
# -*- Mode: Python -*-

# License: Simplified BSD.
# http://www.opensource.org/licenses/bsd-license.html

# Python implementation of the "Intelligent Mail Barcode", the
#   new[ish] U.S. standard for postal barcode encoding.

# The 'letter encoding' is thus:
# 'A' == Ascender
# 'D' == Descender
# 'F' == Full/Both
# 'T' == Neither
#
#         F   A   D   T
#         |   |
#         |   |   |   |
#         |       |

# To print the actual code, download the USPSIMBStandard font
# https://ribbs.usps.gov/onecodesolution/download.cfm
# Then use your web browser to print the html generated by the '-h' option.

# https://ribbs.usps.gov/intelligentmail_mailpieces/documents/tech_guides/SPUSPSG.pdf

import sys

W = sys.stderr.write


# Note: this could probably be written much more simply...
def crc11(input1):
    gen_poly = 0x0f35
    FCS = 0x07ff
    data = input1[0] << 5
    pos = 1
    # do the most significant byte skipping the 2 most significant bits
    for bit in range(2, 8):
        if (FCS ^ data) & 0x400:
            FCS = (FCS << 1) ^ gen_poly
        else:
            FCS = FCS << 1
        FCS &= 0x7ff
        data <<= 1
    # do the rest of the bytes
    for byte_index in range(1, 13):
        data = input1[byte_index] << 3
        for bit in range(8):
            if (FCS ^ data) & 0x400:
                FCS = (FCS << 1) ^ gen_poly
            else:
                FCS = FCS << 1
            FCS &= 0x7ff
            data <<= 1
    return FCS


def reverse_int16(input):
    reverse = 0
    for i in range(16):
        reverse <<= 1
        reverse |= input & 1
        input >>= 1
    return reverse


# no clue what this code actually does, it's not explained in the source.
# I assume it's doing some kind of pre-computed table for a hamming code?
def init_n_of_13(n, table_length):
    table = {}
    index_low = 0
    index_hi = table_length - 1
    for i in range(8192):
        bit_count = bin(i).count('1')
        # If we don't have the right number of bits on, go on to the next value
        if bit_count != n:
            continue
        # If the reverse is less than count, we have already visited this pair before
        reverse = reverse_int16(i) >> 3
        if reverse < i:
            continue
        # If Count is symmetric, place it at the first free slot from the end of the
        # list. Otherwise, place it at the first free slot from the beginning of the
        # list AND place Reverse at the next free slot from the beginning of the list
        if i == reverse:
            table[index_hi] = i
            index_hi -= 1
        else:
            table[index_low] = i
            index_low += 1
            table[index_low] = reverse
            index_low += 1
    # Make sure the lower and upper parts of the table meet properly
    if index_low != index_hi + 1:
        raise ValueError(index_low, index_hi)
    return table


def make_inverted_tabs():
    global inverted
    inverted = {}
    for k, v in tab5.items():
        if v in inverted:
            raise ValueError
        inverted[v] = (0, k)
    for k, v in tab2.items():
        if v in inverted:
            raise ValueError
        inverted[v] = (1, k)


def binary_to_codewords(n):
    r = []
    n, x = divmod(n, 636)
    r.append(x)
    for i in range(9):
        n, x = divmod(n, 1365)
        r.append(x)
    r.reverse()
    return r


def codewords_to_binary(codes):
    n = 0
    cr = codes[:]
    for code in cr[:-1]:
        n = (n * 1365) + code
    n = (n * 636) + cr[-1]
    return n


def convert_routing_code(zip):
    zip = str(zip)
    if len(zip) == 0:
        return 0
    elif len(zip) == 5:
        return int(zip) + 1
    elif len(zip) == 9:
        return int(zip) + 100000 + 1
    elif len(zip) == 11:
        return int(zip) + 1000000000 + 100000 + 1
    else:
        raise ValueError(zip)


def unconvert_routing_code(n):
    # Must be done in this order to avoid a negative return value in a case like a ZIP code of 999984444
    if n > 0:
        n -= 1
    if n > 100000:
        n -= 100000
    if n > 1000000000:
        n -= 1000000000
    return n


def convert_tracking_code(enc, track):
    assert (len(track) == 20)
    enc = (enc * 10) + int(track[0])
    enc = (enc * 5) + int(track[1])
    for i in range(2, 20):
        enc = (enc * 10) + int(track[i])
    return enc


def unconvert_tracking_code(n):
    r = []
    for i in range(2, 20):
        n, x = divmod(n, 10)
        r.append(x)
    n, x = divmod(n, 5)
    r.append(x)
    n, x = divmod(n, 10)
    r.append(x)
    r.reverse()
    return n, ''.join([str(int(x)) for x in r])


def to_bytes(val, nbytes):
    r = []
    for i in range(nbytes):
        r.append(val & 0xff)
        val >>= 8
    r.reverse()
    return r


def encode(barcode_id, service_type_id, mailer_id, serial, delivery):
    n = convert_routing_code(delivery)
    if (str(mailer_id)[0] == '9') or (len(str(mailer_id))==9):
        tracking = '%02d%03d%09d%06d' % (
            barcode_id,
            service_type_id,
            mailer_id,
            serial
        )
    else:
        tracking = '%02d%03d%06d%09d' % (
            barcode_id,
            service_type_id,
            mailer_id,
            serial
        )
    n = convert_tracking_code(n, tracking)
    # convert to bytes for byte-based crc11 fun
    fcs = crc11(to_bytes(n, 13))
    codewords = binary_to_codewords(n)
    codewords[9] *= 2
    if fcs & (1 << 10):
        codewords[0] += 659
    r = []
    for b in codewords:
        if b < 1287:
            r.append(tab5[b])
        elif 127 <= b <= 1364:
            r.append(tab2[b - 1287])
        else:
            raise ValueError
    for i in range(10):
        if fcs & 1 << i:
            r[i] = r[i] ^ 0x1fff
    return make_bars(r)


# the bits from the table seem scattered, there's probably some
#   logic behind the table that I haven't grokked yet...
def make_bars(code):
    r = []
    for i in range(65):
        index, bit = tableA[i]
        ascend = (code[index] & (1 << bit) != 0)
        index, bit = tableD[i]
        descend = (code[index] & (1 << bit) != 0)
        r.append('TADF'[descend << 1 | ascend])
    return ''.join(r)


def unbar(code):
    assert (len(code) == 65)
    r = [0] * 10
    for i in range(65):
        ch = code[i]
        ia, ba = tableA[i]
        id, bd = tableD[i]
        if ch == 'A':
            r[ia] |= 1 << ba
        elif ch == 'D':
            r[id] |= 1 << bd
        elif ch == 'F':
            r[ia] |= 1 << ba
            r[id] |= 1 << bd
        else:
            pass
    return r


def decode(codes):
    fcs = 0
    codes = unbar(codes)
    r = []
    for i in range(10):
        code = codes[i]
        if not code in inverted:
            code = code ^ 0x1fff
            fcs |= 1 << i
        bump, val = inverted[code]
        if bump:
            val += 1287
        r.append(val)
    if r[0] >= 659:
        fcs |= 1 << 10
        r[0] -= 659
    r[9] >>= 1
    binary = codewords_to_binary(r)
    fcs0 = crc11(to_bytes(binary, 13))
    decimal = '%020d' % (int(binary),)
    a, tracking = unconvert_tracking_code(binary)
    routing = unconvert_routing_code(a)
    routing = '%d' % (routing,)
    print('routing', routing)
    if len(routing) == 11:
        print('zip %s-%s delivery point %s' % (routing[:5], routing[5:9], routing[9:]))
    elif len(routing) == 9:
        print('zip %s-%s' % (routing[:5], routing[5:9]))
    elif len(routing) == 5:
        print('zip %s' % (routing[:5],))
    else:
        print('zip: empty')
    print('tracking', tracking)
    barcode_id = tracking[0:2]
    service_type = tracking[2:5]
    if tracking[5] == '9':
        mailer_id = tracking[5:5 + 9]
        serial = tracking[5 + 9:5 + 9 + 6]
    else:
        mailer_id = tracking[5:5 + 6]
        serial = tracking[5 + 6:5 + 6 + 9]
    print('barcode_id', barcode_id)
    print('service_type', service_type)
    print('mailer_id', mailer_id)
    print('serial', serial)


def render_ascii(code):
    "render the letter sequence into something resembling the actual bar code"
    center = ['|'] * 65
    blank = [' '] * 65
    r = blank[:], center[:], blank[:]
    for i in range(65):
        if code[i] == 'A':
            r[0][i] = '|'
        elif code[i] == 'D':
            r[2][i] = '|'
        elif code[i] == 'F':
            r[0][i] = '|'
            r[2][i] = '|'
        else:
            pass
    import sys
    W = sys.stderr.write
    for x in r:
        W(''.join(x) + '\n')


def render_html(code):
    sys.stdout.write(
        '\n'.join([
            '<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">',
            '<html> <head>',
            '<title></title>',
            '</head>',
            '<body>',
            '<p style="font-family:USPSIMBStandard;font-size:16pt">',
            code,
            '</p></body></html>\n',
        ])
    )


def process_bar_table():
    "convert the bar table from the spec into something more usable."
    global tableA, tableD
    tableA = {}
    tableD = {}
    for i in range(65):
        entry = bar_table[i]
        i0, d, i1, a = entry.split()
        i0 = ord(i0) - 65
        i1 = ord(i1) - 65
        d = int(d)
        a = int(a)
        tableD[i] = i0, d
        tableA[i] = i1, a


# last table from the spec, can this be generated?
bar_table = [
    'H 2 E 3', 'B 10 A 0', 'J 12 C 8', 'F 5 G 11', 'I 9 D 1',
    'A 1 F 12', 'C 5 B 8', 'E 4 J 11', 'G 3 I 10', 'D 9 H 6',
    'F 11 B 4', 'I 5 C 12', 'J 10 A 2', 'H 1 G 7', 'D 6 E 9',
    'A 3 I 6', 'G 4 C 7', 'B 1 J 9', 'H 10 F 2', 'E 0 D 8',
    'G 2 A 4', 'I 11 B 0', 'J 8 D 12', 'C 6 H 7', 'F 1 E 10',
    'B 12 G 9', 'H 3 I 0', 'F 8 J 7', 'E 6 C 10', 'D 4 A 5',
    'I 4 F 7', 'H 11 B 9', 'G 0 J 6', 'A 6 E 8', 'C 1 D 2',
    'F 9 I 12', 'E 11 G 1', 'J 5 H 4', 'D 3 B 2', 'A 7 C 0',
    'B 3 E 1', 'G 10 D 5', 'I 7 J 4', 'C 11 F 6', 'A 8 H 12',
    'E 2 I 1', 'F 10 D 0', 'J 3 A 9', 'G 5 C 4', 'H 8 B 7',
    'F 0 E 5', 'C 3 A 10', 'G 12 J 2', 'D 11 B 6', 'I 8 H 9',
    'F 4 A 11', 'B 5 C 2', 'J 1 E 12', 'I 3 G 6', 'H 0 D 7',
    'E 7 H 5', 'A 12 B 11', 'C 9 J 0', 'G 8 F 3', 'D 10 I 2',
]

samples = [
    # example 4 from the spec
    "AADTFFDFTDADTAADAATFDTDDAAADDTDTTDAFADADDDTFFFDDTTTADFAAADFTDAADA",
    # a business reply card - note the 9-digit mailer id
    "FDDAATADTTTFDDADAFFADAFAATFFDDFADFATTAAFDDDDFTTFADFFFDAFFDDFFDDTD",
    # the code printed on the USPS spec documents - their address
    "FAFFATDATTATFFFFTFTFFDTFFDAFDADTTDFAFDAADFTTDATDTATTDFDDTFFFFFTFD",
]


# example 4 from the spec
def t0():
    return encode(1, 234, 567094, 987654321, '01234567891')


# quasi-real address
def t1():
    return encode(0, 700, 123456789, 1, '95008200130')


def run_tests():
    code = t0()
    print(code)
    code = t1()
    decode(code)
    for sample in samples:
        render_ascii(sample)
        decode(sample)


process_bar_table()
tab5 = init_n_of_13(5, 1287)
tab2 = init_n_of_13(2, 78)
make_inverted_tabs()

if __name__ == '__main__':
    if '-t' in sys.argv:
        sys.argv.remove('-t')
        run_tests()
    elif '-d' in sys.argv:
        sys.argv.remove('-d')
        code = sys.argv[1]
        render_ascii(code)
        decode(code)
    elif '-a' in sys.argv:
        sys.argv.remove('-a')
        barcode_id, service_type, mailer, serial, delivery = sys.argv[1:]
        code = encode(int(barcode_id), int(service_type), int(mailer), int(serial), delivery)
        #print(code)
        render_ascii(code)
    elif '-e' in sys.argv:
        sys.argv.remove('-e')
        barcode_id, service_type, mailer, serial, delivery = sys.argv[1:]
        code = encode(int(barcode_id), int(service_type), int(mailer), int(serial), delivery)
        print(code)
    elif '-h' in sys.argv:
        sys.argv.remove('-h')
        barcode_id, service_type, mailer, serial, delivery = sys.argv[1:]
        code = encode(int(barcode_id), int(service_type), int(mailer), int(serial), delivery)
        render_html(code)
    else:
        import sys

        sys.stderr.write(
            "Usage: %s\n"
            "    -t : run tests\n"
            "    -d AAFDTDFDT... : decode\n"
            "    -a barcode-id service-type mailer-id serial delivery : encode to ASCII\n"
            "    -e barcode-id service-type mailer-id serial delivery : encode to ASCII\n"
            "    -h barcode-id service-type mailer-id serial delivery : encode to HTML\n"
            "\n"
            "Example: %s -e 1 700 314159 99999 20500000399\n"
            "   [that's the White House, 1600 Pennsylvania Ave]\n"
            "Note: <delivery> is 5+4 digits of zip, plus 2 digits of delivery point,\n"
            "  (usually the last two digits of the street address).\n" % (
                sys.argv[0], sys.argv[0]
            )
        )
