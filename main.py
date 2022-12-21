import subprocess
from os import path
from json import loads, dump
import numpy as np
from tqdm import tqdm
from substrateinterface import SubstrateInterface
from scalecodec.type_registry import load_type_registry_file

block = 74700

custom_types_path = "custom_types.json"

# repo folder
main_folder = '~/git-repos/sora2-substrate'

# build folder
folder = f'{main_folder}/target/release'

runtime_path = f'{folder}/wbuild/framenode-runtime/framenode_runtime.compact.compressed.wasm'
framenode_path = f'{folder}/framenode'

substrate = SubstrateInterface(
    url='wss://ws.framenode-1.s1.dev.sora2.soramitsu.co.jp',
    ss58_format=69,
    # type_registry_preset='default',
    type_registry=load_type_registry_file(custom_types_path),
)

mktemp = subprocess.run('mktemp', capture_output=True, check=True).stdout.decode('utf-8')
mktemp = path.dirname(mktemp)

subprocess.run(
    f'mkdir -p {mktemp}/data',
    check=True,
    shell=True,
)
subprocess.run(
    f'rm -rf {mktemp}/data/*',
    check=True,
    shell=True,
)
runtime_hex = subprocess.run(
    f'cat {runtime_path} | hexdump -ve \'/1 "%02x"\'',
    capture_output=True,
    check=True,
    shell=True,
).stdout.decode('utf-8')
fork_json = subprocess.run(
    f'{framenode_path} build-spec --chain local --raw',
    check=True,
    capture_output=True,
    shell=True,
).stdout.decode('utf-8')

hash = substrate.get_block_hash(block)
keys = substrate.rpc_request(
    "state_getKeys",
    [
        '0x',
        hash
    ]
)['result']
key_chunks = np.array_split(keys, 100)

state = []

# fetching state
for i in tqdm(key_chunks):
    values = substrate.rpc_request(
        "state_queryStorageAt",
        [
            i.tolist(),
            hash
        ]
    )['result'][0]['changes']
    state += values
state = dict(state)


systemAccountPrefix = '0x26aa394eea5630e07c48ae0c9558cef7b99d880ec681799c0cf30e8886371da9'
state_keys = list(state.keys())
# remove key if it contains system account prefix or this key's value is null
[state.pop(i) for i in state_keys if systemAccountPrefix in i or state.get(i) is None]

# Delete System.LastRuntimeUpgrade to ensure that the on_runtime_upgrade event is triggered
state.pop('0x26aa394eea5630e07c48ae0c9558cef7f9cce9c888469bb1a0dceaa129672ef8')
state['0x3a636f6465'] = '0x' + runtime_hex

#just stole it from the original fork-off script
state['0x5f3e4907f716ac89b6347d15ececedcaf7dad0317324aecae8744b87fc95f2f3'] = '0x02'
state['0x5c0d1176a568c1f92944340dbfed9e9c530ebca703c85910e7164cb7d1c9e47b'] = '0xd43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d'
genesis = loads(fork_json)
genesis['name'] = genesis['name'] + '-fork'
genesis['id'] = genesis['id'] + '-fork'
try:
    genesis['genesis'].pop('runtime')
except KeyError:
    pass

runtime = {
    'top': state,
    'childrenDefault': {}
}

genesis['genesis']['raw'] = runtime
f = open(f'{path.expanduser(main_folder)}/fork.json', 'w')
dump(genesis, f)
f.close()
