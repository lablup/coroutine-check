#! /usr/bin/env python3

import argparse
import asyncio
import ast
import sys
from colorama import init as colorama_init, Fore, Style
from collections import ChainMap


class NotSupportedNodeError(ValueError): pass


def attr2str(node):
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Attribute):
            value = attr2str(node.value)
        elif isinstance(node.value, ast.Name):
            value = node.value.id
        else:
            raise NotSupportedNodeError()
        return value + '.' + attr2str(node.attr)
    elif isinstance(node, str):
        return node
    elif isinstance(node, ast.Name):
        return node.id
    else:
        raise NotSupportedNodeError()


class ImportRetriever(ast.NodeVisitor):

    def __init__(self):
        super().__init__()
        self._user_globals = dict()
        self._user_locals = dict()

    def visit_Import(self, node):
        temp_mod = ast.Module()
        temp_mod.body = [node]
        exec(compile(temp_mod, '<unknown>', 'exec'), self._user_globals, self._user_locals)
        self.generic_visit(node)


class CoroutineDefFinder(ast.NodeVisitor):

    def __init__(self):
        super().__init__()
        self._parent_class = []
        self._parent_func = []
        self._scopes = []
        self._scoped_coros = set()
        self._scoped_types = dict()
        self._level = 0

    def visit_ClassDef(self, node):
        self._parent_class.append((node.name, self._level))
        self._scopes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._parent_func.append((node.name, self._level))
        for deco_node in node.decorator_list:
            try:
                deco_attr = attr2str(deco_node)
                if deco_attr == 'asyncio.coroutine':
                    scoped_coro_sig = '.'.join(self._scopes) + '.' + node.name
                    self._scoped_coros.add(scoped_coro_sig)
                    print(Fore.YELLOW + scoped_coro_sig + Fore.RESET)
            except NotSupportedNodeError:
                pass
        self._scopes.append(node.name)
        for arg in node.args.args:
            if arg.annotation:
                scoped_var = '.'.join(self._scopes) + '.' + arg.arg
                self._scoped_types[scoped_var] = attr2str(arg.annotation)
            # TODO: cover keyword arguments
        self.generic_visit(node)

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Attribute) or isinstance(node.value, ast.Name):
            target = attr2str(node.targets[0])
            value = attr2str(node.value)
            if target.startswith('self.'):
                scoped_target = '.'.join(self._scopes[:-1]) + '.' + target[5:]
            else:
                scoped_target = '.'.join(self._scopes) + '.' + target
            scoped_value = '.'.join(self._scopes) + '.' + value
            t = self._scoped_types.get(scoped_value, None)
            if t is not None:
                self._scoped_types[scoped_target] = t
                #print(scoped_target, ' = ', scoped_value, '|', t)
        self.generic_visit(node)

    def visit(self, node):
        self._level += 1
        super().visit(node)
        if self._parent_class:
            if self._parent_class[-1][1] == self._level:
                self._scopes.pop()
                self._parent_class.pop()
        if self._parent_func:
            if self._parent_func[-1][1] == self._level:
                self._scopes.pop()
                self._parent_func.pop()
        self._level -= 1


class CoroutineChecker(ast.NodeVisitor):

    def __init__(self, ns, scoped_coro_sigs, scoped_types):
        super().__init__()
        self._ns = ns
        self._yield_from = False
        self._parent_class = []
        self._parent_func = []
        self._scopes = []
        self._scoped_coro_sigs = scoped_coro_sigs
        self._scoped_types = scoped_types
        self._level = 0

    def check_if_coroutine(self, callee):
        try:
            e = eval(callee, {}, self._ns)
            return asyncio.iscoroutinefunction(e) or asyncio.iscoroutine(e)
        except NameError:
            pass
        if callee.startswith('self.'):
            target = '.'.join(self._scopes[:-1]) + '.' + callee[5:]
        else:
            target = '.'.join(self._scopes) + '.' + callee
        while True:
            try:
                t = self._scoped_types.get(target, None)
                if t:
                    e = eval(t, {}, self._ns)
                    return asyncio.iscoroutinefunction(e) or asyncio.iscoroutine(e)
                else:
                    if '.' not in target: break
                    target = '.'.join(target.split('.')[:-1])
            except NameError:
                break
        try:
            if callee.startswith('self.'):
                target = '.'.join(self._scopes[:-1]) + '.' + callee[5:]
            else:
                target = '.'.join(self._scopes) + '.' + callee
            print(target)
            ret = target in self._scoped_coro_sigs
            return ret
        except KeyError:
            pass
        #try:
        #    ret = self._lexical_scope_coro[callee]
        #    return ret
        #except KeyError:
        #    #print('lsc fail:', callee, self._lexical_scope_coro)
        #    pass
        return False

    def visit_ClassDef(self, node):
        self._parent_class.append((node.name, self._level))
        self._scopes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._parent_func.append((node.name, self._level))
        self._scopes.append(node.name)
        self.generic_visit(node)

    def visit_YieldFrom(self, node):
        print(Fore.YELLOW + Style.BRIGHT + 'yield from' + Style.RESET_ALL + Fore.RESET, end=' ')
        self._yield_from = True
        self.generic_visit(node)

    def visit_Call(self, node):
        try:
            callee = attr2str(node.func)
            print(Fore.YELLOW + callee + Fore.RESET)
            is_coroutine = self.check_if_coroutine(callee)
            print('  ', end='')
            if is_coroutine:
                if self._yield_from:
                    print(Fore.GREEN, end='')
                else:
                    print(Fore.RED, end='')
                print(callee, 'is coroutine', end='')
            else:
                if self._yield_from:
                    print(Fore.RED, end='')
                else:
                    print(Fore.GREEN, end='')
                print(callee, 'is not coroutine', end='')
            print(Fore.RESET)
        except NotSupportedNodeError:
            pass
        finally:
            self._yield_from = False
            self.generic_visit(node)

    def visit(self, node):
        self._level += 1
        super().visit(node)
        if self._parent_class:
            if self._parent_class[-1][1] == self._level:
                self._scopes.pop()
                self._parent_class.pop()
        if self._parent_func:
            if self._parent_func[-1][1] == self._level:
                self._scopes.pop()
                self._parent_func.pop()
        self._level -= 1

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('filename', type=str)
    args = argparser.parse_args()

    colorama_init()

    with open(args.filename, 'r') as fin:
        node = ast.parse(fin.read())

    ir = ImportRetriever()
    ir.visit(node)
    cd = CoroutineDefFinder()
    cd.visit(node)
    print(cd._scoped_coros)
    print(cd._scoped_types)
    cc = CoroutineChecker(ir._user_locals, cd._scoped_coros, cd._scoped_types)
    cc.visit(node)


if __name__ == '__main__':
    main()
