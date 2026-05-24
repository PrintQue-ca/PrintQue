import { Github } from 'lucide-react'
import { DiscordIcon } from '@/components/icons/DiscordIcon'
import { Button } from '@/components/ui/button'
import { DISCORD_INVITE_URL, GITHUB_REPO_URL } from '@/lib/community-links'

export function CommunityNavLinks() {
  return (
    <>
      <Button variant="ghost" size="icon" className="h-9 w-9" asChild>
        <a
          href={GITHUB_REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="PrintQue on GitHub"
          title="GitHub"
        >
          <Github className="h-5 w-5" />
        </a>
      </Button>
      <Button variant="ghost" size="icon" className="h-9 w-9" asChild>
        <a
          href={DISCORD_INVITE_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Join PrintQue Discord"
          title="Discord"
        >
          <DiscordIcon className="h-5 w-5" />
        </a>
      </Button>
    </>
  )
}
