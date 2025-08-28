"""Creates the infra required to use Pulumi to manage an Azure subscription via GitHub Actions."""

import os
import secrets
from enum import StrEnum

import pulumi
import pulumi_azure
from pulumi_azure_native import authorization
from pulumi_azure_native import resources
from pulumi_azure_native import storage
from pulumi_azure_native import managedidentity

GITHUB_REPOSITORY_OWNER = "microsoft"
GITHUB_REPOSITORY_NAME = "fde"
GITHUB_REPOSITORY_DEFAULT_BRANCH_NAME = "main"

OIDC_TOKEN_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_TOKEN_AUDIENCE = "api://AzureADTokenExchange"

TENANT_IDENTIFIER_ENV_VAR = "TENANT_IDENTIFIER"
MANAGED_IDENTITY_RESOURCE_GROUP_ENV_VAR = "MANAGED_IDENTITY_RESOURCE_GROUP"
MANAGED_IDENTITY_NAME_ENV_VAR = "MANAGED_IDENTITY_NAME"
SERVICE_PRINCIPAL_OBJECT_ID_ENV_VAR = "SERVICE_PRINCIPAL_OBJECT_ID"

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

resource_group = resources.ResourceGroup("pulumi")

# Create the storage account container that will serve as the Pulumi backend
# https://www.pulumi.com/docs/iac/concepts/state-and-backends
storage_account = storage.StorageAccount(
    "pulumi",
    resource_group_name=resource_group.name,
    kind=storage.Kind.STORAGE_V2,
    sku=storage.SkuArgs(
        name=storage.SkuName.STANDARD_LRS,
    ),
)
container = storage.BlobContainer(
    "backend",
    resource_group_name=resource_group.name,
    account_name=storage_account.name,
)

# Set up the app and role assignments for GitHub Actions <> Azure via OpenID Connect (OIDC)
# https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure
# application = azuread.Application(
#     "github-actions",
#     display_name="GitHub Actions",
#     sign_in_audience="AzureADMyOrg",
#     service_management_reference="e764d8a8-22ee-492e-82c0-62f905a66bc1",
# )

# Get already-created UMI
identity = managedidentity.get_user_assigned_identity(
    resource_group_name=managed_identity_resource_group, resource_name=managed_identity_name
)

# Create the federated identity credential that allows the <tenant>-<environment> GitHub Actions
# context to access Azure
# azuread.ApplicationFederatedIdentityCredential(
#     "credential",
#     display_name="environment",
#     application_id=application.object_id.apply(lambda object_id: f"/applications/{object_id}"),
#     issuer=OIDC_TOKEN_ISSUER,
#     audiences=[OIDC_TOKEN_AUDIENCE],
#     subject=f"repo:{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}:environment:{tenant_identifier}-{stack_name}",
# )

# Create the federated identity credential on the UMI that allows the <tenant>-<environment> GitHub Actions
# context to access Azure
fic = managedidentity.FederatedIdentityCredential(
    resource_name=identity.name,
    resource_name_=identity.name,
    resource_group_name=managed_identity_resource_group,
    federated_identity_credential_resource_name="my-fic-name",
    issuer=OIDC_TOKEN_ISSUER,
    audiences=[OIDC_TOKEN_AUDIENCE],
    subject=f"repo:{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}:environment:{tenant_identifier}-{stack_name}",
)

# Create the service principal
# service_principal = azuread.ServicePrincipal(
#     "service-principal",
#     client_id=application.client_id,
# )

# The service principal needs the Contributor role at
# the subscription level in order to manage resources
authorization.RoleAssignment(
    "role-assignment-subscription",
    role_definition_id=make_role_definition_id(BuiltInRole.CONTRIBUTOR),
    principal_id=service_principal_object_id,
    principal_type="ServicePrincipal",
    scope=f"/subscriptions/{azure_config.subscription_id}",
)
# It also needs access to the blob container serving as the Pulumi backend
authorization.RoleAssignment(
    "role-assignment-container",
    role_definition_id=make_role_definition_id(BuiltInRole.STORAGE_BLOB_DATA_CONTRIBUTOR),
    principal_id=service_principal_object_id,
    principal_type="ServicePrincipal",
    scope=pulumi.Output.all(
        subscription_id=azure_config.subscription_id,
        resource_group_name=resource_group.name,
        storage_account_name=storage_account.name,
        container_name=container.name,
    ).apply(
        lambda args: "/".join(
            [
                "",
                "subscriptions",
                args["subscription_id"],
                "resourceGroups",
                args["resource_group_name"],
                "providers",
                "Microsoft.Storage",
                "storageAccounts",
                args["storage_account_name"],
                "blobServices",
                "default",
                "containers",
                args["container_name"],
            ]
        )
    ),
)


def write_secrets(args: dict[str, str]):
    with open(f".secrets-{tenant_identifier}-{stack_name}", "w") as f:
        # Azure OIDC
        f.write(f"AZURE_TENANT_ID={args['tenant_id']}\n")
        f.write(f"AZURE_SUBSCRIPTION_ID={args['subscription_id']}\n")
        f.write(f"AZURE_CLIENT_ID={args['client_id']}\n")

        # Pulumi backend
        f.write(f"PULUMI_AZURE_STORAGE_ACCOUNT={args['storage_account_name']}\n")
        f.write(f"PULUMI_AZURE_CONTAINER={args['container_name']}\n")
        f.write(f"PULUMI_CONFIG_ENCRYPTION_KEY={secrets.token_hex(32)}\n")


pulumi.Output.all(
    client_id=identity.client_id,
    tenant_id=azure_config.tenant_id,
    subscription_id=azure_config.subscription_id,
    storage_account_name=storage_account.name,
    container_name=container.name,
).apply(write_secrets)
