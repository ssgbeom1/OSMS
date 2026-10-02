"""Compact and fielded representations of Python abstract syntax trees."""
import ast,json

def adapt(text,representation='fielded'):
    if representation not in ('fielded','compact'):raise ValueError(representation)
    tree=ast.parse(text,type_comments=True)
    metadata={}
    def term(symbol,children):
        m={'arity':'rank','rank':len(children),'order':'ordered','prefix':0}
        if symbol in metadata and metadata[symbol]!=m:raise AssertionError('signature collision')
        metadata[symbol]=m
        return [symbol,children]
    def encode(value):
        if isinstance(value,ast.AST):
            fields=list(ast.iter_fields(value));kind=type(value).__name__
            if representation=='compact':
                label='ast:'+json.dumps([kind,[k for k,_ in fields]],ensure_ascii=True,separators=(',',':'))
                return term(label,[encode(v) for _,v in fields])
            return term('ast:'+kind,[term('field:'+kind+':'+k,[encode(v)]) for k,v in fields])
        if isinstance(value,list):return term('list:'+str(len(value)),[encode(x) for x in value])
        if value is None:literal=['none','']
        elif value is Ellipsis:literal=['ellipsis','']
        elif isinstance(value,bool):literal=['bool',str(value)]
        elif isinstance(value,int):literal=['int',str(value)]
        elif isinstance(value,float):literal=['float',value.hex()]
        elif isinstance(value,complex):literal=['complex',value.real.hex(),value.imag.hex()]
        elif isinstance(value,str):literal=['str',value]
        elif isinstance(value,bytes):literal=['bytes',value.hex()]
        else:raise TypeError(type(value))
        return term('literal:'+json.dumps(literal,ensure_ascii=True,separators=(',',':')),[])
    root=encode(tree)
    return {'roots':[root],'metadata':metadata,'representation':representation,
            'native_ast_nodes':sum(1 for _ in ast.walk(tree)), 'top_level_statements':len(tree.body),
            'python_ast_dump':ast.dump(tree,annotate_fields=True,include_attributes=False)}


def decode(root,representation):
    def value(t):
        label,cs=t
        if label.startswith('literal:'):
            data=json.loads(label[8:]);tag,x=data[:2]
            if tag=='none':return None
            if tag=='ellipsis':return Ellipsis
            if tag=='bool':return x=='True'
            if tag=='int':return int(x)
            if tag=='float':return float.fromhex(x)
            if tag=='complex':return complex(float.fromhex(x),float.fromhex(data[2]))
            if tag=='str':return x
            if tag=='bytes':return bytes.fromhex(x)
            raise ValueError(tag)
        if label.startswith('list:'):return [value(c) for c in cs]
        if not label.startswith('ast:'):raise ValueError(label)
        if representation=='compact':
            kind,fields=json.loads(label[4:]);items=zip(fields,cs)
        else:
            kind=label[4:];items=[]
            for child in cs:
                prefix='field:'+kind+':'
                if not child[0].startswith(prefix) or len(child[1])!=1:raise ValueError('field wrapper')
                items.append((child[0][len(prefix):],child[1][0]))
        klass=getattr(ast,kind)
        return klass(**{name:value(child) for name,child in items})
    return ast.dump(value(root),annotate_fields=True,include_attributes=False)
