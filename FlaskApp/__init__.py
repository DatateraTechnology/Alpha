from flask import Flask, jsonify, render_template
from ocean_lib.ocean.ocean import Ocean
from ocean_lib.config import Config
from ocean_lib.web3_internal.wallet import Wallet
from ocean_lib.web3_internal.currency import to_wei
from flask_swagger import swagger
from ocean_lib.data_provider.data_service_provider import DataServiceProvider
from ocean_lib.services.service import Service
from ocean_lib.common.agreements.service_types import ServiceTypes
from ocean_lib.assets import trusted_algorithms
from ocean_lib.web3_internal.constants import ZERO_ADDRESS
from ocean_lib.models.compute_input import ComputeInput
import pickle, numpy, time
from matplotlib import pyplot
from azure.storage.blob import BlobClient
import urllib.request, json
import os, uuid

app = Flask(__name__)

@app.route("/")
def index():
    return (
        "Try /hello/Chris for parameterized Flask route.\n"
        "Try /module for module import guidance"
    )

@app.route("/hello/<name>", methods=['GET'])
def hello(name: str):
    return f"hello {name}"

@app.route('/api')
def get_api():
    return render_template('swaggerui.html')

config = Config('config.ini')
ocean = Ocean(config)

print(f"config.network_url = '{config.network_url}'")
print(f"config.metadata_cache_uri = '{config.metadata_cache_uri}'")
print(f"config.provider_url = '{config.provider_url}'")

#Constants
Alice_Wallet_Private_Key = "0x5d75837394b078ce97bc289fa8d75e21000573520bfa7784a9d28ccaae602bf8"
Bob_Wallet_Private_Key = "0xef4b441145c1d0f3b4bc6d61d29f5c6e502359481152f869247c7a4244d45209"

Dataset_Url = "https://raw.githubusercontent.com/trentmc/branin/main/branin.arff"
Algorithm_Url = "https://raw.githubusercontent.com/trentmc/branin/main/gpr.py"

#Create Wallet for Data Provider
alice_wallet = Wallet(ocean.web3, Alice_Wallet_Private_Key, 
config.block_confirmations, config.transaction_timeout)

#Create Wallet for Data Consumer
bob_wallet = Wallet(ocean.web3, Bob_Wallet_Private_Key, 
config.block_confirmations, config.transaction_timeout)

#Create Data Provider Wallet
@app.route("/alpha/createwallet", methods=["GET"], endpoint='create_wallet')
def create_wallet():

    return jsonify(f"alice_wallet.address = '{alice_wallet.address}'")

@app.route("/alpha/fullflow", methods=["GET"], endpoint='full_flow')
def full_flow():

    DATA_datatoken = ocean.create_data_token('DAT', 'DAT', alice_wallet, blob=ocean.config.metadata_cache_uri)
    DATA_datatoken.mint(alice_wallet.address, to_wei(100), alice_wallet)

    ALG_datatoken = ocean.create_data_token('ALG', 'ALG', alice_wallet, blob=ocean.config.metadata_cache_uri)
    ALG_datatoken.mint(alice_wallet.address, to_wei(100), alice_wallet)

    DATA_metadata = {
    "main": {
        "type": "dataset",
        "files": [
	  {
	    "url": Dataset_Url,
	    "index": 0,
	    "contentType": "text/text"
	  }
	],
	"name": "branin", "author": "Trent", "license": "CC0",
	"dateCreated": "2019-12-28T10:55:11Z"}
    }

    DATA_service_attributes = {
    "main": {
        "name": "DATA_dataAssetAccessServiceAgreement",
        "creator": Alice_Wallet_Private_Key,
        "timeout": 3600 * 24,
        "datePublished": "2019-12-28T10:55:11Z",
        "cost": 1.0}
    }

    provider_url = DataServiceProvider.get_url(ocean.config)

    DATA_compute_service = Service(
        service_endpoint = provider_url,
        service_type = ServiceTypes.CLOUD_COMPUTE,
        attributes = DATA_service_attributes)
 
    DATA_ddo = ocean.assets.create(
    metadata = DATA_metadata,
    publisher_wallet = alice_wallet,
    services = [DATA_compute_service],
    data_token_address = DATA_datatoken.address)

    ALG_metadata =  {
    "main": {
        "type": "algorithm",
        "algorithm": {
            "language": "python",
            "format": "docker-image",
            "version": "0.1",
            "container": {
              "entrypoint": "python $ALGO",
              "image": "oceanprotocol/algo_dockers",
              "tag": "python-branin"
            }
        },
        "files": [
	  {
	    "url": Algorithm_Url,
	    "index": 0,
	    "contentType": "text/text",
	  }
	],
	"name": "gpr", "author": "Trent", "license": "CC0",
	"dateCreated": "2020-01-28T10:55:11Z"}
    }

    ALG_service_attributes = {
            "main": {
                "name": "ALG_dataAssetAccessServiceAgreement",
                "creator": alice_wallet.address,
                "timeout": 3600 * 24,
                "datePublished": "2020-01-28T10:55:11Z",
                "cost": 1.0,
            }
        }

    provider_url = DataServiceProvider.get_url(ocean.config)

    ALG_access_service = Service(
        service_endpoint = provider_url,
        service_type = ServiceTypes.CLOUD_COMPUTE,
        attributes = ALG_service_attributes)

    ALG_ddo = ocean.assets.create(
    metadata = ALG_metadata,
    publisher_wallet = alice_wallet,
    services = [ALG_access_service],
    data_token_address = ALG_datatoken.address)

    trusted_algorithms.add_publisher_trusted_algorithm(DATA_ddo, ALG_ddo.did, config.metadata_cache_uri)
    ocean.assets.update(DATA_ddo, publisher_wallet = alice_wallet)
    
    DATA_datatoken.transfer(bob_wallet.address, to_wei(5), from_wallet = alice_wallet)
    ALG_datatoken.transfer(bob_wallet.address, to_wei(5), from_wallet = alice_wallet)

    compute_service_type = "compute"
    compute_service_index = 4
    algo_service_type = "access"
    algo_service_index = 3

    dataset_order_requirements = ocean.assets.order(
    DATA_ddo.did, bob_wallet.address, service_type = compute_service_type)
    
    DATA_order_tx_id = ocean.assets.pay_for_service(
    ocean.web3,
    dataset_order_requirements.amount,
    dataset_order_requirements.data_token_address,
    DATA_ddo.did,
    compute_service_index,
    ZERO_ADDRESS,
    bob_wallet,
    dataset_order_requirements.computeAddress)

    algo_order_requirements = ocean.assets.order(
    ALG_ddo.did, bob_wallet.address, service_type = algo_service_type)
    
    ALG_order_tx_id = ocean.assets.pay_for_service(
        ocean.web3,
        algo_order_requirements.amount,
        algo_order_requirements.data_token_address,
        ALG_ddo.did,
        algo_service_index,
        ZERO_ADDRESS,
        bob_wallet,
        algo_order_requirements.computeAddress)

    DATA_DDO = ocean.assets.resolve(DATA_ddo.did)
    compute_service = DATA_DDO.get_service('compute')

    compute_inputs = [ComputeInput(DATA_ddo.did, DATA_order_tx_id, compute_service.index)]
    job_id = ocean.compute.start(
    compute_inputs,
    bob_wallet,
    algorithm_did = ALG_ddo.did,
    algorithm_tx_id = ALG_order_tx_id,
    algorithm_data_token = ALG_datatoken.address)

    time.sleep(30)

    print(f"Job Status: {ocean.compute.status(DATA_ddo.did, job_id, bob_wallet)}")

    time.sleep(30)

    print(f"Job Status: {ocean.compute.status(DATA_ddo.did, job_id, bob_wallet)}")

    time.sleep(30)

    print(f"Job Status: {ocean.compute.status(DATA_ddo.did, job_id, bob_wallet)}")

    result = ocean.compute.result_file(DATA_ddo.did, job_id, 0, bob_wallet)
    print(f"Result: {result}")

    model = pickle.loads(result)

    X0_vec = numpy.linspace(-5., 10., 15)
    X1_vec = numpy.linspace(0., 15., 15)
    X0, X1 = numpy.meshgrid(X0_vec, X1_vec)
    b, c, t = 0.12918450914398066, 1.5915494309189535, 0.039788735772973836
    u = X1 - b*X0**2 + c*X0 - 6
    r = 10.*(1. - t) * numpy.cos(X0) + 10
    Z = u**2 + r

    fig, ax = pyplot.subplots(subplot_kw={"projection": "3d"})
    ax.scatter(X0, X1, model, c="r", label="model")
    pyplot.title("Data + model")

    local_path = os.path.expanduser("~/Sample")
    if not os.path.exists(local_path):
            os.makedirs(os.path.expanduser("~/Sample"))
    local_file_name = "Result_" + str(uuid.uuid4()) + ".png"
    full_path_to_file = os.path.join(local_path, local_file_name)
    pyplot.savefig(full_path_to_file)

    blob = BlobClient.from_connection_string("DefaultEndpointsProtocol=https;AccountName=datateraalpha;AccountKey=W890/aL1FprdvAsAV4xXpOof1BZQm5Ujb044t8s2XaHFeA0QBYlffI+KYG72uQCg6Ly8SNkeRki8cOwma4co9A==;EndpointSuffix=core.windows.net", container_name="alpha", blob_name=local_file_name)
    with open(full_path_to_file, "rb") as data:
        blob.upload_blob(data)
    
    url = "https://datateraalpha.blob.core.windows.net/alpha/" + local_file_name
    return jsonify(f"Job Status: {ocean.compute.status(DATA_ddo.did, job_id, bob_wallet)} Result: {url}")

if __name__ == "__main__":
    app.run()
