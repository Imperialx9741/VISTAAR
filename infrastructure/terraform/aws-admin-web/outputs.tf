output "amplify_app_id" {
  value = aws_amplify_app.admin_web.id
}

output "amplify_default_domain" {
  description = "The auto-generated *.amplifyapp.com URL Amplify assigns — usable immediately, before any custom domain is configured."
  value       = "${var.git_branch}.${aws_amplify_app.admin_web.default_domain}"
}
