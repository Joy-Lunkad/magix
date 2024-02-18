import re
import logging

from functools import partial

import numpy as np
import jax
from jax.sharding import PartitionSpec as PS
from jax.sharding import NamedSharding, Mesh
from jax.experimental import mesh_utils


logger = logging.getLogger(__name__)


def get_sharding(k, v, sharding_config=None, mesh=None):
    def get_key(x):
        return str(getattr(x, 'key', getattr(x, 'idx', None)))
    
    path = '/'.join([get_key(p) for p in k])
    rule = PS(None)
    for param_name, sharding_rule in sharding_config.items():
        if re.search(param_name, path):
            rule = sharding_rule
            break
    if len(v.shape) == 0:
        rule = PS()

    return NamedSharding(mesh, rule)


def item_sharding(pytree):
    return jax.tree_map(lambda x: x.sharding, pytree)


def initialize_opt_state(optimizer, sharded_params, sharding_config, mesh):
    get_sharding_fn = partial(
        get_sharding,
        sharding_config=sharding_config,
        mesh=mesh
    )
    opt_shapes = jax.eval_shape(optimizer.init, sharded_params)
    opt_sharding = jax.tree_util.tree_map_with_path(get_sharding_fn, opt_shapes)
    opt_state =  jax.jit(optimizer.init, out_shardings=opt_sharding)(sharded_params)
    logger.info("Optimizer shards initialized on devices")
    return opt_state


def create_device_mesh(shape, names=('data', 'model')):
    if -1 in shape:
        from collections import Counter
        assert Counter(shape)[-1] == 1, "Only one -1 is allowed in shape"
        shape = np.array(jax.devices()).reshape(shape).shape

    return Mesh(devices=mesh_utils.create_device_mesh(shape), axis_names=names)