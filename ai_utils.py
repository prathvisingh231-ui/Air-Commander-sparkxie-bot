from __future__ import annotations
import ast, operator as op, discord
from discord.ext import commands
OPS={ast.Add:op.add,ast.Sub:op.sub,ast.Mult:op.mul,ast.Div:op.truediv,ast.Mod:op.mod,ast.Pow:op.pow,ast.USub:op.neg}
def calc(n):
    def ev(x):
        if isinstance(x,ast.Constant) and isinstance(x.value,(int,float)): return x.value
        if isinstance(x,ast.UnaryOp) and type(x.op) in OPS: return OPS[type(x.op)](ev(x.operand))
        if isinstance(x,ast.BinOp) and type(x.op) in OPS: return OPS[type(x.op)](ev(x.left),ev(x.right))
        raise ValueError
    return ev(ast.parse(n,mode='eval').body)
def setup(bot):
    if bot.get_command('calc') is None:
        @bot.command(name='calc')
        async def calc_prefix(ctx, *, expression:str):
            try: await ctx.send(f"🧮 **Result:** `{calc(expression)}`")
            except Exception: await ctx.send('❌ Invalid calculation.')
    if bot.tree.get_command('calc') is None:
        @bot.tree.command(name='calc',description='Calculate a mathematical expression')
        async def calc_slash(i:discord.Interaction, expression:str):
            try: await i.response.send_message(f"🧮 **Result:** `{calc(expression)}`")
            except Exception: await i.response.send_message('❌ Invalid calculation.',ephemeral=True)
