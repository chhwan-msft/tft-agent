"""Creates the infra required to use Pulumi to manage an Azure subscription via GitHub Actions."""

import os
from enum import StrEnum

import pulumi
import pulumi_azure
import uuid
from pulumi_azure_native import managedidentity, search, cognitiveservices, authorization, storage
import pulumi_azure_native_cognitiveservices_v20250601 as azure_native_cognitiveservices_v20250601
# import __editable___pulumi_azure_native_cognitiveservices_v20250601_3_7_1_finder as azure_native_cognitiveservices_v20250601

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
rg_name = "DefaultResourceGroup-EUS"

# ----- Storage Account -----
# For storing structured TFT data in blobs, they will be used as datasources for indexers
stg_name = "chhwanplmistg"
storage_account = storage.StorageAccount(
    stg_name[:24],
    resource_group_name=rg_name,
    kind=storage.Kind.STORAGE_V2,
    sku=storage.SkuArgs(
        name=storage.SkuName.STANDARD_LRS,
    ),
)

# ----- Azure Search Service -----
# For performing RAG over TFT data, to ground agent
service = search.Service(
    "service",
    hosting_mode=search.HostingMode.DEFAULT,
    location=location,
    partition_count=1,
    replica_count=1,
    resource_group_name=rg_name,
    search_service_name=f"chhwansearchpulumi{pulumi.get_stack()}",
    sku={
        "name": search.SkuName.BASIC,
    },
    identity=search.IdentityArgs(type=search.IdentityType.SYSTEM_ASSIGNED),
)

# ----- AI Foundry Project -----
# 2) AI Foundry resource = Cognitive Services Account (kind 'AIServices')
# TODO: Update to azure_native_cognitiveservices_v20250601 to enable project management flag + change resource name
acct = azure_native_cognitiveservices_v20250601.Account(
    f"chhwanfdryv2pulumi{pulumi.get_stack()}",
    resource_group_name=rg_name,
    account_name=f"chhwanfdryv2pulumi{pulumi.get_stack()}",  # must be globally unique within region
    location=location,
    kind="AIServices",
    sku=azure_native_cognitiveservices_v20250601.SkuArgs(name="S0"),
    properties=azure_native_cognitiveservices_v20250601.AccountPropertiesArgs(
        public_network_access="Enabled",  # or "Disabled" + networkAcls, etc.
        # allow_project_management=True, # Only available in later api versions i.e. v202050601
        # optional: custom_sub_domain_name="myfoundryacct123",
    ),
    identity=azure_native_cognitiveservices_v20250601.IdentityArgs(
        type=azure_native_cognitiveservices_v20250601.ResourceIdentityType.SYSTEM_ASSIGNED
    ),
)

# 3) Foundry Project under the Account (accounts/projects)
# TODO: Create once account can support project management
proj = cognitiveservices.Project(
    f"chhwanfdryprojectpulumi{pulumi.get_stack()}",
    resource_group_name=rg_name,
    account_name=acct.name,  # establishes dependency on the parent
    project_name=f"chhwanfdryprojectpulumi{pulumi.get_stack()}",
    location=location,
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
    principal_type=authorization.PrincipalType.SERVICE_PRINCIPAL,
)

foundry_account_role = authorization.RoleAssignment(
    f"fdryaccountcontributor{pulumi.get_stack()}",
    scope=acct.id,
    principal_id=identity.principal_id,
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    role_assignment_name=str(uuid.uuid4()),
    principal_type=authorization.PrincipalType.SERVICE_PRINCIPAL,
)

# TODO: Enable once foundry project is created
# foundry_project_role = authorization.RoleAssignment(
#     f"fdryprojectcontributor{pulumi.get_stack()}",
#     scope=proj.id,
#     principal_id=identity.principal_id,
#     role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
#     role_assignment_name=str(uuid.uuid4()),
#     principal_type=authorization.PrincipalType.SERVICE_PRINCIPAL
# )

# Grant the Search service's system-assigned identity Contributor on the Foundry acct
search_service_identity_role = authorization.RoleAssignment(
    f"searchsvcprojectcontributor{pulumi.get_stack()}",
    scope=acct.id,
    principal_id=service.identity.principal_id,
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    role_assignment_name=str(uuid.uuid4()),
    principal_type=authorization.PrincipalType.SERVICE_PRINCIPAL,
)

# 3) Foundry model deployment under the Account
# Choose a logical name for this deployment under the account
deployment_name = "gpt4o-globalstd"
deployment = cognitiveservices.Deployment(
    "gpt4o-deployment",
    account_name=acct.name,
    resource_group_name=rg_name,
    deployment_name=deployment_name,
    sku=cognitiveservices.SkuArgs(
        name="GlobalStandard",  # Standard / global processing SKU
        capacity=1,
    ),
    properties=cognitiveservices.DeploymentPropertiesArgs(
        model=cognitiveservices.DeploymentModelArgs(
            format="OpenAI",  # For Azure OpenAI models
            name="gpt-4o",
            version="2024-11-20",
        ),
        # Optional dials if you want them later:
        # version_upgrade_option="OnceNewDefaultVersionAvailable",
        rai_policy_name="Microsoft.Default",
        # scale_settings=cs.DeploymentScaleSettingsArgs(scale_type="Standard", capacity=1),
    ),
)
