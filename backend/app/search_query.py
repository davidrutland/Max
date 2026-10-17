"""Deterministic Boolean query parser and literal message matcher; no database access.

Precedence: unary > AND (including adjacency) > OR. Unary + is a global
requirement across OR branches. Search is case-insensitive Unicode casefold.
Terms match complete whitespace-delimited tokens with edge punctuation ignored
only when it is not part of the query. Internal punctuation remains significant.
"""
import re

class QuerySyntaxError(ValueError):
    pass


def tokenize(query):
    out = []
    i = 0
    while i < len(query):
        if query[i].isspace():
            i += 1; continue
        start = i
        c = query[i]
        if c in '()|+':
            out.append((c, c, i)); i += 1; continue
        if c == '-' and not query.startswith('--', i) and (i == 0 or query[i-1].isspace() or query[i-1] in '(|+'):
            out.append(('-', '-', i)); i += 1; continue
        if c == '"':
            i += 1; buf = []
            while i < len(query) and query[i] != '"':
                if query[i] == '\\' and i+1 < len(query) and query[i+1] in ('"', '\\'):
                    i += 1
                buf.append(query[i]); i += 1
            if i == len(query): raise QuerySyntaxError(f'Unterminated quote at {start}')
            i += 1
            if not ''.join(buf).strip(): raise QuerySyntaxError(f'Empty phrase at {start}')
            out.append(('PHRASE', ''.join(buf), start)); continue
        while i < len(query) and not query[i].isspace() and query[i] not in '()|+"':
            i += 1
        value = query[start:i]
        if value in ('AND', 'OR', 'NOT'):
            out.append((value, value, start))
        elif value.startswith('-') and not value.startswith('--') and len(value)>1 and (start == 0 or query[start-1].isspace() or query[start-1] in '(|+'):
            out.extend([('-', '-', start), ('TERM', value[1:], start+1)])
        else:
            out.append(('TERM', value, start))
    out.append(('EOF', '', len(query)))
    return out


class _Parser:
    def __init__(self, tokens): self.tokens, self.pos = tokens, 0
    def peek(self): return self.tokens[self.pos][0]
    def take(self, kind=None):
        t = self.tokens[self.pos]
        if kind is not None and t[0] != kind: raise QuerySyntaxError(f'Expected {kind} at {t[2]}')
        self.pos += 1
        return t
    def parse(self):
        if self.peek() == 'EOF': raise QuerySyntaxError('Empty query')
        ast = self.or_expr()
        if self.peek() != 'EOF':
            t = self.tokens[self.pos]
            raise QuerySyntaxError(f'Unexpected {t[1]!r} at {t[2]}')
        return ast
    def or_expr(self):
        node = self.and_expr()
        while self.peek() in ('OR', '|'):
            self.take(); node = ('OR', node, self.and_expr())
        return node
    def and_expr(self):
        node = self.unary()
        while self.peek() in ('AND', 'TERM', 'PHRASE', '(', 'NOT', '-', '+'):
            if self.peek() == 'AND': self.take()
            node = ('AND', node, self.unary())
        return node
    def unary(self):
        if self.peek() in ('NOT', '-', '+'):
            kind = self.take()[0]
            return ('REQUIRE' if kind == '+' else 'NOT', self.unary())
        if self.peek() == '(':
            self.take(); node = self.or_expr(); self.take(')'); return node
        if self.peek() == 'PHRASE': return ('PHRASE', self.take()[1])
        if self.peek() == 'TERM':
            value = self.take()[1]
            if not value or value == '*' or ('*' in value and (value.count('*') != 1 or not value.endswith('*'))):
                raise QuerySyntaxError(f'Invalid wildcard term: {value!r}')
            return ('PREFIX', value[:-1]) if value.endswith('*') else ('TERM', value)
        raise QuerySyntaxError(f'Expected search term at {self.tokens[self.pos][2]}')


def parse(query):
    ast = _Parser(tokenize(query)).parse()
    def validate(node, under_not=False):
        if node[0] == 'REQUIRE' and under_not:
            raise QuerySyntaxError("Global + requirement cannot appear inside NOT")
        if node[0] == 'NOT':
            validate(node[1], True)
        elif node[0] == 'REQUIRE':
            validate(node[1], under_not)
        elif node[0] in ('AND', 'OR'):
            validate(node[1], under_not)
            validate(node[2], under_not)
    validate(ast)
    return ast


def _word_pattern(value, prefix=False):
    # Require a token boundary without splitting technical tokens at punctuation.
    # A leading/trailing punctuation character is significant when queried.
    v = re.escape(value.casefold())
    left = r'(?<![^\W_])' if value[0].isalnum() else r'(?<!\S)'
    right = r'(?![^\W_])' if value[-1].isalnum() and not prefix else (r'[^\s]*' if prefix else r'(?!\S)')
    return re.compile(left + v + right)


def _literal_match(kind, value, text):
    t = text.casefold()
    if kind == 'PHRASE':
        return value.casefold() in t
    if kind == 'PREFIX':
        # Prefix applies to a whitespace-delimited token, not arbitrary substrings.
        return any(tok.startswith(value.casefold()) for tok in t.split())
    return bool(_word_pattern(value).search(t))


def matches(ast, text):
    """Evaluate all global + requirements regardless of Boolean short-circuiting."""
    requirements = []
    def collect(node):
        if node[0] == 'REQUIRE':
            requirements.append(node[1])
            collect(node[1])
        elif node[0] in ('AND', 'OR'):
            collect(node[1]); collect(node[2])
        elif node[0] == 'NOT':
            collect(node[1])
    collect(ast)
    def evaluate(node):
        op = node[0]
        if op in ('TERM', 'PHRASE', 'PREFIX'):
            return _literal_match(op, node[1], text)
        if op == 'NOT': return not evaluate(node[1])
        if op == 'REQUIRE': return True
        if op == 'AND': return evaluate(node[1]) and evaluate(node[2])
        if op == 'OR': return evaluate(node[1]) or evaluate(node[2])
        raise ValueError(f'Unknown AST node {op}')
    return evaluate(ast) and all(evaluate(node) for node in requirements)


def search(query, messages):
    """Return matching (id, text) pairs from synthetic (id, text) messages."""
    ast = parse(query)
    return [(id_, content) for id_, content in messages if matches(ast, content)]
