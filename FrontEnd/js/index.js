function createStars() {
  const starsContainer = document.getElementById("stars");
  for (let i = 0; i < 150; i++) {
    const star = document.createElement("div");
    star.className = "star" + (Math.random() > 0.3 ? " purple" : "");
    star.style.left = `${Math.random() * 100}%`;
    star.style.top = `${Math.random() * 100}%`;
    star.style.animationDelay = `${Math.random() * 2}s`;
    starsContainer.appendChild(star);
  }
}

window.addEventListener("load", () => {
  createStars();
});