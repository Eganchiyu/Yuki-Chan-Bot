#!/usr/bin/env python3
"""A simple Brainfuck interpreter.

Supported commands: + - < > [ ] . ,
- Memory: 30000 bytes (cells)
- I/O: stdin / stdout
- Errors on: unmatched brackets, instruction pointer out of range,
  data pointer out of range.
"""
import sys

MEM_SIZE = 30000


def parse(code):
    """Validate brackets and build the jump table. Returns (code, jump)."""
    code = ''.join(c for c in code if c in '+-<>[].,')
    stack = []
    jump = {}
    for i, c in enumerate(code):
        if c == '[':
            stack.append(i)
        elif c == ']':
            if not stack:
                raise SyntaxError("unmatched ']' at position %d" % i)
            j = stack.pop()
            jump[i] = j
            jump[j] = i
    if stack:
        raise SyntaxError("unmatched '[' at position %d" % stack[-1])
    return code, jump


def run(code):
    code, jump = parse(code)
    mem = bytearray(MEM_SIZE)
    ptr = 0
    ip = 0
    n = len(code)

    while ip < n:  # reaching the end of the program halts normally
        if not (0 <= ip < n):
            raise RuntimeError("instruction pointer out of range: %d" % ip)
        c = code[ip]
        if c == '>':
            ptr += 1
            if ptr >= MEM_SIZE:
                raise RuntimeError("data pointer out of range: %d" % ptr)
        elif c == '<':
            ptr -= 1
            if ptr < 0:
                raise RuntimeError("data pointer out of range: %d" % ptr)
        elif c == '+':
            mem[ptr] = (mem[ptr] + 1) & 0xFF
        elif c == '-':
            mem[ptr] = (mem[ptr] - 1) & 0xFF
        elif c == '.':
            sys.stdout.write(chr(mem[ptr]))
            sys.stdout.flush()
        elif c == ',':
            ch = sys.stdin.read(1)
            mem[ptr] = ord(ch) if ch else 0
        elif c == '[':
            if mem[ptr] == 0:
                ip = jump[ip]
        elif c == ']':
            if mem[ptr] != 0:
                ip = jump[ip]
        ip += 1


def main():
    if len(sys.argv) < 2:
        print("usage: brainfuck.py <program.bf>", file=sys.stderr)
        return 2
    with open(sys.argv[1], 'r') as f:
        code = f.read()
    try:
        run(code)
    except (SyntaxError, RuntimeError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
