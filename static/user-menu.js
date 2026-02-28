/**
 * User Menu Dropdown
 * Handles the toggle and close functionality for the user menu dropdown
 */

document.addEventListener('DOMContentLoaded', function () {
    const userMenuToggle = document.getElementById('userMenuToggle');
    const userDropdown = document.getElementById('userDropdown');

    if (userMenuToggle && userDropdown) {
        // Toggle dropdown on user menu click
        userMenuToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            userMenuToggle.classList.toggle('active');
            userDropdown.classList.toggle('show');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function (e) {
            if (!userMenuToggle.contains(e.target)) {
                userMenuToggle.classList.remove('active');
                userDropdown.classList.remove('show');
            }
        });

        // Close dropdown when a link is clicked
        userDropdown.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', function () {
                userMenuToggle.classList.remove('active');
                userDropdown.classList.remove('show');
            });
        });
    }
});
