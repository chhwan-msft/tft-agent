"""Creates the infra required to use Pulumi to manage an Azure subscription via GitHub Actions."""

import os
from enum import StrEnum

import pulumi
import pulumi_azure
from pulumi_azure_native import managedidentity, search, cognitiveservices
from pulumi_azure_native import authorization
import uuid

GITHUB_REPOSITORY_OWNER = "chhwan-msft"
GITHUB_REPOSITORY_NAME = "tft-agent"

OIDC_TOKEN_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_TOKEN_AUDIENCE = "api://AzureADTokenExchange"

TENANT_IDENTIFIER_ENV_VAR = "TENANT_IDENTIFIER_ENV_VAR"
MANAGED_IDENTITY_RESOURCE_GROUP_ENV_VAR = "MANAGED_IDENTITY_RESOURCE_GROUP_ENV_VAR"
MANAGED_IDENTITY_NAME_ENV_VAR = "MANAGED_IDENTITY_NAME_ENV_VAR"
SERVICE_PRINCIPAL_OBJECT_ID_ENV_VAR = "SERVICE_PRINCIPAL_OBJECT_ID_ENV_VAR"

# Users should set the tenant identifier via environment variable
# before running `pulumi up` on this project.
tenant_identifier = os.environ.get(TENANT_IDENTIFIER_ENV_VAR)

if not tenant_identifier:
    raise ValueError(f"{TENANT_IDENTIFIER_ENV_VAR} environment variable is not set.")

managed_identity_resource_group = os.environ.get(MANAGED_IDENTITY_RESOURCE_GROUP_ENV_VAR)

if not managed_identity_resource_group:
    raise ValueError(f"{MANAGED_IDENTITY_RESOURCE_GROUP_ENV_VAR} environment variable is not set.")

managed_identity_name = os.environ.get(MANAGED_IDENTITY_NAME_ENV_VAR)

if not managed_identity_name:
    raise ValueError(f"{MANAGED_IDENTITY_NAME_ENV_VAR} environment variable is not set.")

service_principal_object_id = os.environ.get(SERVICE_PRINCIPAL_OBJECT_ID_ENV_VAR)

if not service_principal_object_id:
    raise ValueError(f"{SERVICE_PRINCIPAL_OBJECT_ID_ENV_VAR} environment variable is not set.")


class BuiltInRole(StrEnum):
    CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
    STORAGE_BLOB_DATA_CONTRIBUTOR = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"


def make_role_definition_id(role: BuiltInRole) -> str:
    return "/".join(
        [
            "",
            "subscriptions",
            azure_config.subscription_id,
            "providers",
            "Microsoft.Authorization",
            "roleDefinitions",
            role.value,
        ]
    )


azure_config = pulumi_azure.core.get_subscription()
stack_name = pulumi.get_stack()

print(f"Azure tenant ID: {azure_config.tenant_id}")
print(f"Azure subscription ID: {azure_config.subscription_id}")
print(f"Tenant identifier: {tenant_identifier}")
print(f"Pulumi stack name: {stack_name}")

# Get already-created UMI
identity = managedidentity.get_user_assigned_identity(
    resource_group_name=managed_identity_resource_group, resource_name=managed_identity_name
)

config = pulumi.Config()
location = config.get("location") or "East US"

# Get already created resource group
rg = pulumi_azure.core.ResourceGroup(
    "DefaultResourceGroup-EUS",
    name="DefaultResourceGroup-EUS",
    location=location,
)

# ----- Storage Account -----
stg_name = (f"chhwanpulumi{pulumi.get_stack()}").lower()
stg = pulumi_azure.storage.Account(
    stg_name,
    name=stg_name[:24],
    location=rg.location,
    resource_group_name=rg.name,
    account_tier="Standard",
    account_replication_type="LRS",
)

# Create a blob container to be used by Pulumi backend/state or uploads
container = pulumi_azure.storage.Container(
    "backend",
    storage_account_name=stg.name,
    container_access_type="private",
)

# ----- Azure Search Service -----
service = search.Service(
    "service",
    hosting_mode=search.HostingMode.DEFAULT,
    location=rg.location,
    partition_count=1,
    replica_count=1,
    resource_group_name=rg.name,
    search_service_name=f"chhwansearchpulumi{pulumi.get_stack()}",
    sku={
        "name": search.SkuName.BASIC,
    },
    identity=search.IdentityArgs(type=search.IdentityType.SYSTEM_ASSIGNED),
)

# ----- AI Foundry Project -----
# 2) AI Foundry resource = Cognitive Services Account (kind 'AIServices')
acct = cognitiveservices.Account(
    f"chhwanfdrypulumi{pulumi.get_stack()}",
    resource_group_name=rg.name,
    account_name=f"chhwanfdrypulumi{pulumi.get_stack()}",  # must be globally unique within region
    location=rg.location,
    kind="AIServices",
    sku=cognitiveservices.SkuArgs(name="S0"),
    properties=cognitiveservices.AccountPropertiesArgs(
        public_network_access="Enabled",  # or "Disabled" + networkAcls, etc.
        # optional: custom_sub_domain_name="myfoundryacct123",
    ),
    identity=cognitiveservices.IdentityArgs(type=cognitiveservices.ResourceIdentityType.SYSTEM_ASSIGNED),
)
1
# 3) Foundry Project under the Account (accounts/projects)
proj = cognitiveservices.Project(
    f"chhwanfdryrojectpulumi{pulumi.get_stack()}",
    resource_group_name=rg.name,
    account_name=acct.name,  # establishes dependency on the parent
    project_name=f"chhwanfdryprojectpulumi{pulumi.get_stack()}",
    location=rg.location,
    identity=cognitiveservices.IdentityArgs(type=cognitiveservices.ResourceIdentityType.SYSTEM_ASSIGNED),
    properties=cognitiveservices.ProjectPropertiesArgs(
        display_name="Pulumi Foundry Project",
        description="Created with Pulumi Azure Native",
    ),
)

# Grant the user-assigned managed identity Contributor role on Search Service and Foundry resources
# Use azure-native authorization RoleAssignment resources; each needs a GUID name.
search_role = authorization.RoleAssignment(
    f"searchcontributor{pulumi.get_stack()}",
    scope=service.id,
    principal_id=identity.principal_id,
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    role_assignment_name=str(uuid.uuid4()),
)

foundry_account_role = authorization.RoleAssignment(
    f"fdryaccountcontributor{pulumi.get_stack()}",
    scope=acct.id,
    principal_id=identity.principal_id,
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    role_assignment_name=str(uuid.uuid4()),
)

foundry_project_role = authorization.RoleAssignment(
    f"fdryprojectcontributor{pulumi.get_stack()}",
    scope=proj.id,
    principal_id=identity.principal_id,
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    role_assignment_name=str(uuid.uuid4()),
)

# Grant the Search service's system-assigned identity Contributor on the Foundry project
search_service_identity_role = authorization.RoleAssignment(
    f"searchsvcprojectcontributor{pulumi.get_stack()}",
    scope=proj.id,
    principal_id=service.identity.principal_id,
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    role_assignment_name=str(uuid.uuid4()),
)
