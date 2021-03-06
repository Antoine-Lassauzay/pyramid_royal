import logging
from functools import wraps

from pyramid.view import view_defaults, view_config
from pyramid.httpexceptions import (
    HTTPCreated,
    HTTPConflict,
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPMethodNotAllowed,
)

from royal import exceptions as exc
from royal import interfaces

log = logging.getLogger(__name__)


def includeme(config):
    config.scan('royal.views')


class BaseView(object):

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def wrap_dict(self, item, item_dict):
        result = {'links': dict((k, self.request.resource_url(v))
                                for k, v in item.links.iteritems())}
        if item_dict:
            result.update({item.resource_name: item_dict})
        return result

    def resource_url(self, *elements, **kw):
        return self.request.resource_url(self.context, *elements, **kw)


def get_params(request):
    try:
        return request.POST.mixed()
    except Exception:
        log.debug('Error parsing POST', exc_info=True)
        raise HTTPBadRequest('Error parsing request parameters')


@view_defaults(context=interfaces.ICollection, renderer='royal')
class CollectionView(BaseView):

    @view_config(request_method='GET', permission='index')
    def index(self):
        func = self.context.index

        if hasattr(self.context, 'index_schema'):
            params = self.context.index_schema(self.request.GET.mixed())
            result = func(**params)
        else:
            result = func(**get_params(self.request))

        return result

    @view_config(request_method='POST', permission='create')
    def create(self):
        func = self.context.create

        params = get_params(self.request)
        if hasattr(self.context, 'create_schema'):
            params = self.context.create_schema(params)

        item = func(params)

        self.request.response.headers['Location'] = item.url()
        self.request.response.status_int = HTTPCreated.code

        return item.show()


@view_defaults(context=interfaces.IItem, renderer='royal')
class ItemView(BaseView):

    @view_config(request_method='GET', permission='show')
    @view_config(request_method='GET', permission='show',
                 context=interfaces.IRoot)
    def show(self):
        func = self.context.show
        params = get_params(self.request)
        return func(**params)

    @view_config(request_method='PUT', permission='replace')
    def put(self):
        func = self.context.replace
        params = get_params(self.request)
        return func(params)

    @view_config(request_method='PATCH', permission='update')
    def patch(self):
        func = self.context.update
        func(get_params(self.request))
        return self.request.response


@view_config(context=interfaces.IItem, request_method='DELETE',
             permission='delete', renderer='royal')
@view_config(context=interfaces.ICollection, request_method='DELETE',
             permission='delete', renderer='royal')
def delete(context, request):
    context.delete()
    return {}


@view_config(context=exc.MethodNotAllowed, renderer='royal')
@view_config(context=interfaces.IBase, renderer='royal')
def not_allowed(context, request):
    request.response.status_int = HTTPMethodNotAllowed.code
    return {
        'error': 'method_not_allowed',
        'resource': request.resource_url(context.resource
                                         if hasattr(context, 'resource')
                                         else context),
        'http_method': request.method
    }


def log_error_dict(view_callable):
    @wraps(view_callable)
    def wrapper(context, request):
        result = view_callable(context, request)
        log.debug('%s: %s', type(context), result, exc_info=True)
        return result
    return wrapper


@view_config(context=exc.NotFound, renderer='royal', decorator=log_error_dict)
def item_not_found(context, request):
    request.response.status_int = HTTPNotFound.code
    return {
        'error': 'not_found',
        'resource': request.resource_url(context.resource)
    }


@view_config(context=exc.Conflict, renderer='royal', decorator=log_error_dict)
def conflict(context, request):
    request.response.status_int = HTTPConflict.code
    return {
        'error': 'already_exists',
        'resource': request.resource_url(context.resource)
    }


@view_config(context='voluptuous.MultipleInvalid',
             renderer='royal', decorator=log_error_dict)
def invalid_parameters(context, request):
    request.response.status_int = HTTPBadRequest.code
    return {
        'error': 'invalid_parameters',
        'message': unicode(context)
    }


@view_config(context=exc.BadParameter, renderer='royal',
             decorator=log_error_dict)
def bad_parameter(context, request):
    request.response.status_int = HTTPBadRequest.code
    return {
        'error': 'invalid_parameters',
        'resource': request.resource_url(context.resource),
        'message': '%s="%s"' % (context.name, context.value),
        }


@view_config(context=Exception, renderer='royal', decorator=log_error_dict)
def exception(context, request):
    request.response.status_int = HTTPInternalServerError.code
    return {
        'error': 'unexpected_error',
        'message': unicode(context),
        'error_class': type(context).__name__,
    }
