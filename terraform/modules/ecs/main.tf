# ECS Cluster and Services - Simplified for EC2 deployment

# Note: This is a simplified module stub
# The actual ECS infrastructure is complex and requires the full deployment scripts
# For production deployment, use the existing scripts in /scripts/deploy-to-ecs-ec2.sh

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

# Security Group for ECS
resource "aws_security_group" "ecs" {
  name        = "${var.name_prefix}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Application Port"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-ecs-sg"
    }
  )
}

# Outputs for use by deployment scripts
output "cluster_id" {
  value = aws_ecs_cluster.main.id
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

# Placeholder outputs - actual values come from deployment scripts
output "service_name" {
  value = "${var.name_prefix}-backend-service"
}

output "alb_dns_name" {
  value = "use-deployment-scripts"
}

output "alb_zone_id" {
  value = "use-deployment-scripts"
}

output "ec2_instance_id" {
  value = "use-deployment-scripts"
}

output "ec2_public_ip" {
  value = "use-deployment-scripts"
}
