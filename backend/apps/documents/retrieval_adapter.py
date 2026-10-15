"""Permission boundary for an injected W3 retriever; no model or index mocks here."""
import math
from .exceptions import DocumentError
from .models import DocumentVersion
from .retrieval_contracts import Chunk,RetrievalScope
from .retrieval_scope import resolve_scope


def live_scope(user,scope):
    if not isinstance(scope,RetrievalScope) or scope.user_id!=str(user.pk):
        raise DocumentError('INVALID_SCOPE','Server-owned scope required.',400)
    current=resolve_scope(user,scope.course_id,scope.classroom_id,scope.session_id,
                          scope.document_ids,scope.mode,scope.preview)
    if current!=scope:raise DocumentError('SCOPE_CHANGED','Sources changed. Resolve scope again.',409)
    return current


def retrieve_authorized(user,query,scope,retriever,top_k=5,*,catalog):
    """Catalog must come from load_catalog(server_owned_manifest), not request data.

    Provider interface: search(query=..., allowed_version_ids=tuple, top_k=int)
    returns a list of {chunk_id, score}; provider text/source are never trusted.
    """
    if not isinstance(query,str) or not query.strip() or len(query)>8000:
        raise DocumentError('INVALID_QUERY','A nonempty query up to 8000 characters is required.',400)
    if type(top_k) is not int or not 1<=top_k<=10:
        raise DocumentError('INVALID_TOP_K','top_k must be an integer between 1 and 10.',400)
    current=live_scope(user,scope)
    if not current.allowed_version_ids:return []
    try:hits=retriever.search(query=query.strip(),allowed_version_ids=current.allowed_version_ids,top_k=top_k)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError('RETRIEVAL_UNAVAILABLE','Retrieval service/index unavailable.',503) from exc
    live_scope(user,current)
    if not isinstance(hits,list) or len(hits)>top_k:
        raise DocumentError('INVALID_RETRIEVAL','Invalid retrieval output.',503)
    versions={str(v.pk):v for v in DocumentVersion.objects.filter(pk__in=current.allowed_version_ids)}
    seen=set();results=[]
    for hit in hits:
        if not isinstance(hit,dict):raise DocumentError('INVALID_RETRIEVAL','Invalid retrieval hit.',503)
        cid=hit.get('chunk_id');score=hit.get('score')
        if not isinstance(cid,str) or type(score) not in (int,float):
            raise DocumentError('INVALID_RETRIEVAL','Invalid chunk ID or score type.',503)
        try:score=float(score)
        except (ValueError,OverflowError) as exc:
            raise DocumentError('INVALID_RETRIEVAL','Invalid score range.',503) from exc
        chunk=catalog.get(cid)
        if (cid in seen or not isinstance(chunk,Chunk) or not math.isfinite(score)):
            raise DocumentError('INVALID_RETRIEVAL','Unknown/duplicate chunk or invalid score.',503)
        seen.add(cid);version=versions.get(chunk.version_id)
        if (not version or chunk.chunk_id!=cid or chunk.course_id!=current.course_id
                or chunk.document_id!=str(version.document_id) or chunk.source_checksum!=version.checksum_sha256
                or type(chunk.page_number) is not int or not 1<=chunk.page_number<=version.page_count):
            raise DocumentError('INVALID_RETRIEVAL','Chunk provenance does not match allowed source.',503)
        results.append({'chunk_id':cid,'score':float(score),'text':chunk.text,
            'source':{'course_id':chunk.course_id,'document_id':chunk.document_id,'version_id':chunk.version_id,
                      'document_title':chunk.document_title,'page_number':chunk.page_number,'section_title':chunk.section_title}})
    # Final live checks also cover mutations between provider return and provenance validation.
    live_scope(user,current)
    results.sort(key=lambda hit:(-hit['score'],hit['chunk_id']))
    for i,hit in enumerate(results):hit['rank']=i+1
    return results
