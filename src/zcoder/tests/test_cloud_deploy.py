"""Tests for zcoder.agent.orchestration.cloud_deploy - Cloud deployment support."""

from __future__ import annotations

import pytest

from zcoder.agent.orchestration.cloud_deploy import (
    CloudDeployer,
    CloudDeployment,
    CloudProvider,
    CloudProviderAWS,
    CloudProviderAzure,
    CloudProviderConfig,
    CloudProviderGCP,
    CloudProviderType,
    CloudResource,
    DeploymentPlan,
    DeploymentStatus,
    DeploymentStep,
    create_cloud_deployer,
)


class TestCloudProviderType:
    """Tests for CloudProviderType enum."""

    def test_values(self):
        assert CloudProviderType.AWS == "aws"
        assert CloudProviderType.GCP == "gcp"
        assert CloudProviderType.AZURE == "azure"
        assert CloudProviderType.LOCAL == "local"


class TestDeploymentStatus:
    """Tests for DeploymentStatus enum."""

    def test_values(self):
        assert DeploymentStatus.PENDING == "pending"
        assert DeploymentStatus.PROVISIONING == "provisioning"
        assert DeploymentStatus.DEPLOYING == "deploying"
        assert DeploymentStatus.CONFIGURING == "configuring"
        assert DeploymentStatus.HEALTH_CHECKING == "health_checking"
        assert DeploymentStatus.ACTIVE == "active"
        assert DeploymentStatus.FAILED == "failed"
        assert DeploymentStatus.DESTROYED == "destroyed"


class TestCloudProviderConfig:
    """Tests for CloudProviderConfig dataclass."""

    def test_creation(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        assert config.provider_type == CloudProviderType.AWS
        assert config.region == "us-east-1"
        assert config.credentials == {}
        assert config.project_id is None
        assert config.subscription_id is None
        assert config.default_zone is None

    def test_creation_full(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.GCP,
            region="us-central1",
            credentials={"key": "value"},
            project_id="my-project",
            subscription_id="sub-123",
            default_zone="us-central1-a",
        )
        assert config.provider_type == CloudProviderType.GCP
        assert config.region == "us-central1"
        assert config.credentials == {"key": "value"}
        assert config.project_id == "my-project"
        assert config.subscription_id == "sub-123"
        assert config.default_zone == "us-central1-a"


class TestCloudResource:
    """Tests for CloudResource dataclass."""

    def test_creation(self):
        resource = CloudResource(
            id="res_1",
            type="vm",
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        assert resource.id == "res_1"
        assert resource.type == "vm"
        assert resource.provider_type == CloudProviderType.AWS
        assert resource.region == "us-east-1"
        assert resource.status == "pending"
        assert resource.ip_address is None
        assert resource.dns_name is None
        assert resource.tags == {}
        assert resource.created_at > 0
        assert resource.metadata == {}


class TestDeploymentStep:
    """Tests for DeploymentStep dataclass."""

    def test_creation(self):
        step = DeploymentStep(
            id="step_1",
            name="Create VM",
            description="Create a new VM instance",
        )
        assert step.id == "step_1"
        assert step.name == "Create VM"
        assert step.description == "Create a new VM instance"
        assert step.depends_on == []
        assert step.status == DeploymentStatus.PENDING
        assert step.resource_ids == []
        assert step.started_at is None
        assert step.completed_at is None
        assert step.error is None

    def test_duration(self):
        step = DeploymentStep(
            id="step_1",
            name="Create VM",
            description="Create a new VM instance",
            started_at=1000.0,
            completed_at=1005.0,
        )
        assert step.duration == 5.0

    def test_duration_not_started(self):
        step = DeploymentStep(
            id="step_1",
            name="Create VM",
            description="Create a new VM instance",
        )
        assert step.duration == 0.0


class TestDeploymentPlan:
    """Tests for DeploymentPlan dataclass."""

    def test_creation(self):
        plan = DeploymentPlan(
            id="plan_1",
            name="Deploy web app",
            description="Deploy a web application",
            target_provider=CloudProviderType.AWS,
            target_region="us-east-1",
        )
        assert plan.id == "plan_1"
        assert plan.name == "Deploy web app"
        assert plan.description == "Deploy a web application"
        assert plan.target_provider == CloudProviderType.AWS
        assert plan.target_region == "us-east-1"
        assert plan.steps == []
        assert plan.status == DeploymentStatus.PENDING
        assert plan.created_at > 0
        assert plan.started_at is None
        assert plan.completed_at is None
        assert plan.error is None

    def test_completed_steps(self):
        plan = DeploymentPlan(
            id="plan_1",
            name="Test",
            description="Test plan",
            target_provider=CloudProviderType.AWS,
            target_region="us-east-1",
        )
        assert plan.completed_steps == 0
        assert plan.total_steps == 0

        step1 = DeploymentStep(id="s1", name="Step 1", description="First step")
        step1.status = DeploymentStatus.ACTIVE
        step2 = DeploymentStep(id="s2", name="Step 2", description="Second step")
        step2.status = DeploymentStatus.PENDING
        plan.steps = [step1, step2]

        assert plan.completed_steps == 1
        assert plan.total_steps == 2


class TestCloudDeployment:
    """Tests for CloudDeployment dataclass."""

    def test_creation(self):
        deployment = CloudDeployment(
            id="deploy_1",
            name="My App",
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        assert deployment.id == "deploy_1"
        assert deployment.name == "My App"
        assert deployment.provider_type == CloudProviderType.AWS
        assert deployment.region == "us-east-1"
        assert deployment.status == DeploymentStatus.PENDING
        assert deployment.resources == {}
        assert deployment.plan is None
        assert deployment.created_at > 0
        assert deployment.updated_at > 0
        assert deployment.error is None

    def test_resource_count(self):
        deployment = CloudDeployment(
            id="deploy_1",
            name="Test",
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        assert deployment.resource_count == 0

        deployment.resources["r1"] = CloudResource(
            id="r1", type="vm", provider_type=CloudProviderType.AWS, region="us-east-1"
        )
        deployment.resources["r2"] = CloudResource(
            id="r2", type="db", provider_type=CloudProviderType.AWS, region="us-east-1"
        )
        assert deployment.resource_count == 2


class TestCloudProvider:
    """Tests for CloudProvider base class."""

    def test_creation(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        provider = CloudProvider(config)
        assert provider.config == config
        assert provider.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        provider = CloudProvider(config)
        await provider.connect()
        assert provider.is_connected is True
        await provider.disconnect()
        assert provider.is_connected is False

    @pytest.mark.asyncio
    async def test_create_resource_not_implemented(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        provider = CloudProvider(config)
        with pytest.raises(NotImplementedError):
            await provider.create_resource("vm", "test-vm", {})

    @pytest.mark.asyncio
    async def test_health_check(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        provider = CloudProvider(config)
        assert provider.is_connected is False
        assert await provider.health_check() is False

        await provider.connect()
        assert await provider.health_check() is True


class TestCloudProviderAWS:
    """Tests for CloudProviderAWS."""

    @pytest.fixture
    def provider(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
            credentials={"access_key": "test"},
        )
        return CloudProviderAWS(config)

    @pytest.mark.asyncio
    async def test_create_resource(self, provider):
        resource = await provider.create_resource("vm", "my-vm", {"instance_type": "t2.micro"})
        assert resource.id.startswith("aws-vm-")
        assert resource.type == "vm"
        assert resource.provider_type == CloudProviderType.AWS
        assert resource.region == "us-east-1"
        assert resource.status == "running"
        assert resource.ip_address is not None
        assert resource.dns_name is not None
        assert resource.tags["Name"] == "my-vm"
        assert resource.tags["ManagedBy"] == "zcoder"

    @pytest.mark.asyncio
    async def test_delete_resource(self, provider):
        result = await provider.delete_resource("res_1")
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self, provider):
        assert await provider.health_check() is True


class TestCloudProviderGCP:
    """Tests for CloudProviderGCP."""

    @pytest.fixture
    def provider(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.GCP,
            region="us-central1",
            project_id="my-project",
        )
        return CloudProviderGCP(config)

    @pytest.mark.asyncio
    async def test_create_resource(self, provider):
        resource = await provider.create_resource("vm", "my-vm", {"machine_type": "e2-medium"})
        assert resource.id.startswith("gcp-vm-")
        assert resource.type == "vm"
        assert resource.provider_type == CloudProviderType.GCP
        assert resource.region == "us-central1"
        assert resource.status == "running"
        assert resource.metadata["gcp_region"] == "us-central1"
        assert resource.metadata["project"] == "my-project"

    @pytest.mark.asyncio
    async def test_health_check(self, provider):
        assert await provider.health_check() is True


class TestCloudProviderAzure:
    """Tests for CloudProviderAzure."""

    @pytest.fixture
    def provider(self):
        config = CloudProviderConfig(
            provider_type=CloudProviderType.AZURE,
            region="eastus",
            subscription_id="sub-123",
        )
        return CloudProviderAzure(config)

    @pytest.mark.asyncio
    async def test_create_resource(self, provider):
        resource = await provider.create_resource("vm", "my-vm", {"vm_size": "Standard_D2s_v3"})
        assert resource.id.startswith("azure-vm-")
        assert resource.type == "vm"
        assert resource.provider_type == CloudProviderType.AZURE
        assert resource.region == "eastus"
        assert resource.status == "running"
        assert resource.metadata["azure_region"] == "eastus"
        assert resource.metadata["subscription"] == "sub-123"

    @pytest.mark.asyncio
    async def test_health_check(self, provider):
        assert await provider.health_check() is True


class TestCloudDeployer:
    """Tests for CloudDeployer."""

    @pytest.fixture
    def deployer(self):
        return CloudDeployer(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
            credentials={"access_key": "test"},
        )

    def test_creation(self):
        deployer = CloudDeployer(
            provider_type=CloudProviderType.AWS,
            region="us-east-1",
        )
        assert deployer.provider_type == CloudProviderType.AWS
        assert deployer.region == "us-east-1"
        assert deployer.credentials == {}
        assert deployer.provider is None
        assert deployer.deployments == {}

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, deployer):
        await deployer.connect()
        assert deployer.provider is not None
        assert deployer.provider.is_connected is True
        await deployer.disconnect()
        assert deployer.provider is None

    @pytest.mark.asyncio
    async def test_deploy(self, deployer):
        await deployer.connect()
        deployment = await deployer.deploy(
            name="my-app",
            resources=[
                {"type": "vm", "name": "web-server-1"},
                {"type": "db", "name": "database-1"},
            ],
        )
        assert deployment.id.startswith("deploy_")
        assert deployment.name == "my-app"
        assert deployment.provider_type == CloudProviderType.AWS
        assert deployment.region == "us-east-1"
        assert deployment.status == DeploymentStatus.ACTIVE
        assert len(deployment.resources) == 2
        assert deployment.plan is not None
        assert deployment.plan.target_provider == CloudProviderType.AWS

    @pytest.mark.asyncio
    async def test_get_deployment(self, deployer):
        await deployer.connect()
        deployment = await deployer.deploy(
            name="test-app",
            resources=[{"type": "vm", "name": "server-1"}],
        )
        retrieved = deployer.get_deployment(deployment.id)
        assert retrieved is not None
        assert retrieved.id == deployment.id
        assert retrieved.name == "test-app"

    @pytest.mark.asyncio
    async def test_list_deployments(self, deployer):
        await deployer.connect()
        await deployer.deploy(name="app-1", resources=[{"type": "vm", "name": "s1"}])
        await deployer.deploy(name="app-2", resources=[{"type": "db", "name": "db-1"}])
        deployments = deployer.list_deployments()
        assert len(deployments) == 2

    @pytest.mark.asyncio
    async def test_destroy_deployment(self, deployer):
        await deployer.connect()
        deployment = await deployer.deploy(
            name="temp-app",
            resources=[{"type": "vm", "name": "temp-server"}],
        )
        assert len(deployer.deployments) == 1
        result = await deployer.destroy_deployment(deployment.id)
        assert result is True
        assert deployment.status == DeploymentStatus.DESTROYED
        assert len(deployment.resources) == 0

    @pytest.mark.asyncio
    async def test_destroy_nonexistent(self, deployer):
        result = await deployer.destroy_deployment("nonexistent")
        assert result is False


class TestCreateCloudDeployer:
    """Tests for create_cloud_deployer factory function."""

    @pytest.mark.asyncio
    async def test_create_aws(self):
        deployer = await create_cloud_deployer(
            provider_type="aws",
            region="us-west-2",
        )
        assert isinstance(deployer, CloudDeployer)
        assert deployer.provider_type == CloudProviderType.AWS
        assert deployer.region == "us-west-2"

    @pytest.mark.asyncio
    async def test_create_gcp(self):
        deployer = await create_cloud_deployer(
            provider_type="gcp",
            region="us-central1",
            project_id="my-project",
        )
        assert deployer.provider_type == CloudProviderType.GCP
        assert deployer.region == "us-central1"
        assert deployer.project_id == "my-project"

    @pytest.mark.asyncio
    async def test_create_azure(self):
        deployer = await create_cloud_deployer(
            provider_type="azure",
            region="eastus",
            subscription_id="sub-456",
        )
        assert deployer.provider_type == CloudProviderType.AZURE
        assert deployer.region == "eastus"
        assert deployer.subscription_id == "sub-456"
